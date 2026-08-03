import sysconfig
from pathlib import Path
import importlib.metadata as meta
import os

SPLITS = set(["root_core", "root_dataframe", "root_roofit"])

# strict dependency of every other split, so it is present in any wheel installation
CORE_DIST = "root_core"

def normalize_dist_name(name):
    return name.replace("-", "_").lower()

def is_alpha_wheel():
    try:
        wheel_version = meta.version(CORE_DIST)
    except meta.PackageNotFoundError:
        return False
    return "a" in wheel_version # alpha wheels are the only ones shipping split modulemaps

def get_site_packages_path():
    return Path(sysconfig.get_path("platlib"))

def get_m_idx_path():
    m_idx_rel = Path("ROOT/lib/modules.idx")
    return get_site_packages_path() / m_idx_rel

def get_mm_path():
    mm_rel = Path("ROOT/include/ROOT.modulemap")
    return get_site_packages_path() / mm_rel

def is_root_installed(dist_name):
    # this will raise when root isn't installed, which is correct behavior
    # return False should be unreachable
    return True if meta.version(dist_name) else False

def get_newest_dist_info_mtime():
    manifests = get_root_manifests()
    manifest_mtimes = [ os.path.getmtime(manifest) for manifest in manifests ]
    return max(manifest_mtimes) # existence of at least one manifest guaranteed by is_root_installed()

def get_installed_splits():
    manifests = get_root_manifests()
    return [ split for split in COMPONENTS if any(split in str(manifest) for manifest in manifests) ]

def get_stale_splits():
    installed_splits = get_installed_splits()
    return [ split for split in COMPONENTS if split not in installed_splits and is_module_injected(split) ]

# this hardcodes the package names, but that needs to happen anyways for now given the manual patching
def get_root_distributions():
    return [ dist for dist in meta.distributions()
             if normalize_dist_name(dist.name) in SPLITS ]

def get_root_manifests():
    return [ dist._path / "RECORD" for dist in get_root_distributions() ]

def get_m_idx_mtime():
    return os.path.getmtime(get_m_idx_path())

def is_m_idx_stale(m_idx_mtime):
    dist_info_mtime = get_newest_dist_info_mtime()
    print(f"DEBUG: Using module index path: {get_m_idx_path()}")
    print(f"DEBUG: index time: {m_idx_mtime} dist time: {dist_info_mtime}")
    return dist_info_mtime >= m_idx_mtime

def drop_m_idx():
    try:
        get_m_idx_path().unlink()
    except FileNotFoundError: # already dropped, nothing to do
        return
    print("DEBUG: Deleted stale modules.idx")

def drop_m_idx_if_stale(dist_name):
    is_root_installed(dist_name) # will throw on failure

    try:
        m_idx_mtime = get_m_idx_mtime()
    except OSError:
        print("Warning: modules.idx could not be found. Did you delete it manually?")
        return

    if is_m_idx_stale(m_idx_mtime):
        drop_m_idx()

def generate_begin_comment(split_name):
    return f"// BEGIN {split_name}"

def generate_end_comment(split_name):
    return f"// END {split_name}"

def is_module_injected(split_name):
    with open(get_mm_path(), 'r', encoding='utf-8') as f:
        unique_lines = set(f)
    return generate_begin_comment(split_name) + '\n' in unique_lines

def inject_into_mm(installed_splits):
    with open(get_mm_path(), "r", encoding="utf-8") as reader:
        text = reader.read()

    injected = []
    for split_name in installed_splits:
        if is_module_injected(split_name):
            continue
        split_addition = COMPONENTS[split_name]
        text = (text.rstrip("\n") + "\n\n"
                + generate_begin_comment(split_name) + "\n"
                + split_addition + "\n"
                + generate_end_comment(split_name) + "\n")
        injected.append(split_name)

    if injected: # only touch the file when something actually changed
        with open(get_mm_path(), "w", encoding="utf-8") as writer:
            writer.write(text)
        print(f"DEBUG: Injected into ROOT.modulemap: {', '.join(injected)}")

    return injected

def remove_from_mm(stale_splits):
    with open(get_mm_path(), "r", encoding="utf-8", newline="") as reader:
        lines = reader.readlines()
    stripped_lines = [ ln.rstrip("\r\n") for ln in lines ]
    
    removed = []
    for split_name in stale_splits:
        if not is_module_injected(split_name):
            print(f"DEBUG: Tried removing {split_name}, but it isn't present in ROOT.modulemap")
            continue
        begin = stripped_lines.index(generate_begin_comment(split_name))
        end = stripped_lines.index(generate_end_comment(split_name), begin + 1)
        lines = lines[:begin] + lines[end + 1:]
        stripped_lines = stripped_lines[:begin] + stripped_lines[end + 1:]
        removed.append(split_name)

    if removed: # only touch the file when something actually changed
        kept = "".join(lines)
        with open(get_mm_path(), "w", encoding="utf-8", newline="") as writer:
            writer.write(kept)
        print(f"DEBUG: Removed from ROOT.modulemap: {', '.join(removed)}")

    return removed

# returns True when the modulemap was actually changed
def update_mm():
    injected = inject_into_mm(get_installed_splits())
    removed = remove_from_mm(get_stale_splits())
    return bool(injected or removed)

# entry point for import ROOT
def bootstrap():
    if not is_alpha_wheel(): # not an alpha wheel installation, nothing to do
        return

    try:
        drop_m_idx_if_stale(CORE_DIST)
        if update_mm(): # the index no longer describes the modulemap we just patched
            drop_m_idx()
    except Exception as e:
        print(f"Warning: could not reconcile the ROOT module map: {e}")


COMPONENTS = {
    'root_dataframe': '''module "ROOTDataFrame" {
  requires cplusplus
  module "ROOT/RCsvDS.hxx" { header "ROOT/RCsvDS.hxx" export * }
  module "ROOT/RVecDS.hxx" { header "ROOT/RVecDS.hxx" export * }
  module "ROOT/RDataFrame.hxx" { header "ROOT/RDataFrame.hxx" export * }
  module "ROOT/RDataSource.hxx" { header "ROOT/RDataSource.hxx" export * }
  module "ROOT/RDFHelpers.hxx" { header "ROOT/RDFHelpers.hxx" export * }
  module "ROOT/RLazyDS.hxx" { header "ROOT/RLazyDS.hxx" export * }
  module "ROOT/RResultHandle.hxx" { header "ROOT/RResultHandle.hxx" export * }
  module "ROOT/RResultPtr.hxx" { header "ROOT/RResultPtr.hxx" export * }
  module "ROOT/RRootDS.hxx" { header "ROOT/RRootDS.hxx" export * }
  module "ROOT/RSnapshotOptions.hxx" { header "ROOT/RSnapshotOptions.hxx" export * }
  module "ROOT/RTrivialDS.hxx" { header "ROOT/RTrivialDS.hxx" export * }
  module "ROOT/RTTreeDS.hxx" { header "ROOT/RTTreeDS.hxx" export * }
  module "ROOT/RDF/ActionHelpers.hxx" { header "ROOT/RDF/ActionHelpers.hxx" export * }
  module "ROOT/RDF/ColumnReaderUtils.hxx" { header "ROOT/RDF/ColumnReaderUtils.hxx" export * }
  module "ROOT/RDF/GraphNode.hxx" { header "ROOT/RDF/GraphNode.hxx" export * }
  module "ROOT/RDF/GraphUtils.hxx" { header "ROOT/RDF/GraphUtils.hxx" export * }
  module "ROOT/RDF/HistoModels.hxx" { header "ROOT/RDF/HistoModels.hxx" export * }
  module "ROOT/RDF/InterfaceUtils.hxx" { header "ROOT/RDF/InterfaceUtils.hxx" export * }
  module "ROOT/RDF/RActionBase.hxx" { header "ROOT/RDF/RActionBase.hxx" export * }
  module "ROOT/RDF/RAction.hxx" { header "ROOT/RDF/RAction.hxx" export * }
  module "ROOT/RDF/RActionSnapshot.hxx" { header "ROOT/RDF/RActionSnapshot.hxx" export * }
  module "ROOT/RDF/RActionImpl.hxx" { header "ROOT/RDF/RActionImpl.hxx" export * }
  module "ROOT/RDF/RColumnRegister.hxx" { header "ROOT/RDF/RColumnRegister.hxx" export * }
  module "ROOT/RDF/RNewSampleNotifier.hxx" { header "ROOT/RDF/RNewSampleNotifier.hxx" export * }
  module "ROOT/RDF/RSampleInfo.hxx" { header "ROOT/RDF/RSampleInfo.hxx" export * }
  module "ROOT/RDF/RDefineBase.hxx" { header "ROOT/RDF/RDefineBase.hxx" export * }
  module "ROOT/RDF/RDefaultValueFor.hxx" { header "ROOT/RDF/RDefaultValueFor.hxx" export * }
  module "ROOT/RDF/RDefine.hxx" { header "ROOT/RDF/RDefine.hxx" export * }
  module "ROOT/RDF/RDefinePerSample.hxx" { header "ROOT/RDF/RDefinePerSample.hxx" export * }
  module "ROOT/RDF/RDefineReader.hxx" { header "ROOT/RDF/RDefineReader.hxx" export * }
  module "ROOT/RDF/RDSColumnReader.hxx" { header "ROOT/RDF/RDSColumnReader.hxx" export * }
  module "ROOT/RDF/RColumnReaderBase.hxx" { header "ROOT/RDF/RColumnReaderBase.hxx" export * }
  module "ROOT/RDF/RCutFlowReport.hxx" { header "ROOT/RDF/RCutFlowReport.hxx" export * }
  module "ROOT/RDF/RDatasetSpec.hxx" { header "ROOT/RDF/RDatasetSpec.hxx" export * }
  module "ROOT/RDF/RDisplay.hxx" { header "ROOT/RDF/RDisplay.hxx" export * }
  module "ROOT/RDF/RFilterBase.hxx" { header "ROOT/RDF/RFilterBase.hxx" export * }
  module "ROOT/RDF/RFilter.hxx" { header "ROOT/RDF/RFilter.hxx" export * }
  module "ROOT/RDF/RInterface.hxx" { header "ROOT/RDF/RInterface.hxx" export * }
  module "ROOT/RDF/RInterfaceBase.hxx" { header "ROOT/RDF/RInterfaceBase.hxx" export * }
  module "ROOT/RDF/RJittedAction.hxx" { header "ROOT/RDF/RJittedAction.hxx" export * }
  module "ROOT/RDF/RJittedDefine.hxx" { header "ROOT/RDF/RJittedDefine.hxx" export * }
  module "ROOT/RDF/RJittedFilter.hxx" { header "ROOT/RDF/RJittedFilter.hxx" export * }
  module "ROOT/RDF/RJittedVariation.hxx" { header "ROOT/RDF/RJittedVariation.hxx" export * }
  module "ROOT/RDF/RLazyDSImpl.hxx" { header "ROOT/RDF/RLazyDSImpl.hxx" export * }
  module "ROOT/RDF/RLoopManager.hxx" { header "ROOT/RDF/RLoopManager.hxx" export * }
  module "ROOT/RDF/RMergeableValue.hxx" { header "ROOT/RDF/RMergeableValue.hxx" export * }
  module "ROOT/RDF/RMetaData.hxx" { header "ROOT/RDF/RMetaData.hxx" export * }
  module "ROOT/RDF/RNodeBase.hxx" { header "ROOT/RDF/RNodeBase.hxx" export * }
  module "ROOT/RDF/RRangeBase.hxx" { header "ROOT/RDF/RRangeBase.hxx" export * }
  module "ROOT/RDF/RRange.hxx" { header "ROOT/RDF/RRange.hxx" export * }
  module "ROOT/RDF/RResultMap.hxx" { header "ROOT/RDF/RResultMap.hxx" export * }
  module "ROOT/RDF/RSample.hxx" { header "ROOT/RDF/RSample.hxx" export * }
  module "ROOT/RDF/RFilterWithMissingValues.hxx" { header "ROOT/RDF/RFilterWithMissingValues.hxx" export * }
  module "ROOT/RDF/RTreeColumnReader.hxx" { header "ROOT/RDF/RTreeColumnReader.hxx" export * }
  module "ROOT/RDF/RVariation.hxx" { header "ROOT/RDF/RVariation.hxx" export * }
  module "ROOT/RDF/RVariationBase.hxx" { header "ROOT/RDF/RVariationBase.hxx" export * }
  module "ROOT/RDF/RVariationReader.hxx" { header "ROOT/RDF/RVariationReader.hxx" export * }
  module "ROOT/RDF/RVariationsDescription.hxx" { header "ROOT/RDF/RVariationsDescription.hxx" export * }
  module "ROOT/RDF/RVariedAction.hxx" { header "ROOT/RDF/RVariedAction.hxx" export * }
  module "ROOT/RDF/SnapshotHelpers.hxx" { header "ROOT/RDF/SnapshotHelpers.hxx" export * }
  module "ROOT/RDF/Utils.hxx" { header "ROOT/RDF/Utils.hxx" export * }
  module "ROOT/RDF/PyROOTHelpers.hxx" { header "ROOT/RDF/PyROOTHelpers.hxx" export * }
  module "ROOT/RDF/RDFDescription.hxx" { header "ROOT/RDF/RDFDescription.hxx" export * }
  module "ROOT/RNTupleDS.hxx" { header "ROOT/RNTupleDS.hxx" export * }
  link "libROOTDataFrame.so"
  export *
}
 
module "ROOTMLDataLoader" {
  requires cplusplus
  module "ROOT/ML/RDataLoaderEngine.hxx" { header "ROOT/ML/RDataLoaderEngine.hxx" export * }
  module "ROOT/ML/RBatchLoader.hxx" { header "ROOT/ML/RBatchLoader.hxx" export * }
  module "ROOT/ML/RClusterLoader.hxx" { header "ROOT/ML/RClusterLoader.hxx" export * }
  module "ROOT/ML/RFlat2DMatrix.hxx" { header "ROOT/ML/RFlat2DMatrix.hxx" export * }
  module "ROOT/ML/RFlat2DMatrixOperators.hxx" { header "ROOT/ML/RFlat2DMatrixOperators.hxx" export * }
  module "ROOT/ML/RDatasetLoader.hxx" { header "ROOT/ML/RDatasetLoader.hxx" export * }
  module "ROOT/ML/RSampler.hxx" { header "ROOT/ML/RSampler.hxx" export * }
  link "libROOTMLDataLoader.so"
  export *
}''',
    'root_roofit': '''module "RooFitCodegen" {
  requires cplusplus
  module "RooFit/CodegenImpl.h" { header "RooFit/CodegenImpl.h" export * }
  link "libRooFitCodegen.so"
  export *
}
 
module "RooFitCore" {
  requires cplusplus
  module "Roo1DTable.h" { header "Roo1DTable.h" export * }
  module "RooAICRegistry.h" { header "RooAICRegistry.h" export * }
  module "RooAbsAnaConvPdf.h" { header "RooAbsAnaConvPdf.h" export * }
  module "RooAbsArg.h" { header "RooAbsArg.h" export * }
  module "RooAbsBinning.h" { header "RooAbsBinning.h" export * }
  module "RooAbsCache.h" { header "RooAbsCache.h" export * }
  module "RooAbsCacheElement.h" { header "RooAbsCacheElement.h" export * }
  module "RooAbsCachedPdf.h" { header "RooAbsCachedPdf.h" export * }
  module "RooAbsCachedReal.h" { header "RooAbsCachedReal.h" export * }
  module "RooAbsCategory.h" { header "RooAbsCategory.h" export * }
  module "RooAbsCategoryLValue.h" { header "RooAbsCategoryLValue.h" export * }
  module "RooAbsCollection.h" { header "RooAbsCollection.h" export * }
  module "RooAbsData.h" { header "RooAbsData.h" export * }
  module "RooAbsDataHelper.h" { header "RooAbsDataHelper.h" export * }
  module "RooAbsDataStore.h" { header "RooAbsDataStore.h" export * }
  module "RooAbsFunc.h" { header "RooAbsFunc.h" export * }
  module "RooAbsGenContext.h" { header "RooAbsGenContext.h" export * }
  module "RooAbsHiddenReal.h" { header "RooAbsHiddenReal.h" export * }
  module "RooAbsIntegrator.h" { header "RooAbsIntegrator.h" export * }
  module "RooAbsLValue.h" { header "RooAbsLValue.h" export * }
  module "RooAbsMCStudyModule.h" { header "RooAbsMCStudyModule.h" export * }
  module "RooAbsMoment.h" { header "RooAbsMoment.h" export * }
  module "RooAbsPdf.h" { header "RooAbsPdf.h" export * }
  module "RooAbsProxy.h" { header "RooAbsProxy.h" export * }
  module "RooAbsReal.h" { header "RooAbsReal.h" export * }
  module "RooAbsRealLValue.h" { header "RooAbsRealLValue.h" export * }
  module "RooAbsSelfCachedPdf.h" { header "RooAbsSelfCachedPdf.h" export * }
  module "RooAbsSelfCachedReal.h" { header "RooAbsSelfCachedReal.h" export * }
  module "RooAbsStudy.h" { header "RooAbsStudy.h" export * }
  module "RooAddGenContext.h" { header "RooAddGenContext.h" export * }
  module "RooAddModel.h" { header "RooAddModel.h" export * }
  module "RooAddPdf.h" { header "RooAddPdf.h" export * }
  module "RooAddition.h" { header "RooAddition.h" export * }
  module "RooArgList.h" { header "RooArgList.h" export * }
  module "RooArgProxy.h" { header "RooArgProxy.h" export * }
  module "RooArgSet.h" { header "RooArgSet.h" export * }
  module "RooBinSamplingPdf.h" { header "RooBinSamplingPdf.h" export * }
  module "RooBinWidthFunction.h" { header "RooBinWidthFunction.h" export * }
  module "RooBinnedGenContext.h" { header "RooBinnedGenContext.h" export * }
  module "RooBinning.h" { header "RooBinning.h" export * }
  module "RooBinningCategory.h" { header "RooBinningCategory.h" export * }
  module "RooBrentRootFinder.h" { header "RooBrentRootFinder.h" export * }
  module "RooCacheManager.h" { header "RooCacheManager.h" export * }
  module "RooCachedPdf.h" { header "RooCachedPdf.h" export * }
  module "RooCachedReal.h" { header "RooCachedReal.h" export * }
  module "RooCategory.h" { header "RooCategory.h" export * }
  module "RooCategoryProxy.h" { header "RooCategoryProxy.h" export * }
  module "RooChangeTracker.h" { header "RooChangeTracker.h" export * }
  module "RooClassFactory.h" { header "RooClassFactory.h" export * }
  module "RooCmdArg.h" { header "RooCmdArg.h" export * }
  module "RooCmdConfig.h" { header "RooCmdConfig.h" export * }
  module "RooCollectionProxy.h" { header "RooCollectionProxy.h" export * }
  module "RooCompositeDataStore.h" { header "RooCompositeDataStore.h" export * }
  module "RooConstVar.h" { header "RooConstVar.h" export * }
  module "RooConstraintSum.h" { header "RooConstraintSum.h" export * }
  module "RooConvCoefVar.h" { header "RooConvCoefVar.h" export * }
  module "RooConvGenContext.h" { header "RooConvGenContext.h" export * }
  module "RooCurve.h" { header "RooCurve.h" export * }
  module "RooCustomizer.h" { header "RooCustomizer.h" export * }
  module "RooDLLSignificanceMCSModule.h" { header "RooDLLSignificanceMCSModule.h" export * }
  module "RooDataHist.h" { header "RooDataHist.h" export * }
  module "RooDataHistSliceIter.h" { header "RooDataHistSliceIter.h" export * }
  module "RooDataProjBinding.h" { header "RooDataProjBinding.h" export * }
  module "RooDataSet.h" { header "RooDataSet.h" export * }
  module "RooDerivative.h" { header "RooDerivative.h" export * }
  module "RooDirItem.h" { header "RooDirItem.h" export * }
  module "RooDouble.h" { header "RooDouble.h" export * }
  module "RooEffGenContext.h" { header "RooEffGenContext.h" export * }
  module "RooEffProd.h" { header "RooEffProd.h" export * }
  module "RooEfficiency.h" { header "RooEfficiency.h" export * }
  module "RooEllipse.h" { header "RooEllipse.h" export * }
  module "RooErrorHandler.h" { header "RooErrorHandler.h" export * }
  module "RooErrorVar.h" { header "RooErrorVar.h" export * }
  module "RooEvaluatorWrapper.h" { header "RooEvaluatorWrapper.h" export * }
  module "RooExpensiveObjectCache.h" { header "RooExpensiveObjectCache.h" export * }
  module "RooExtendPdf.h" { header "RooExtendPdf.h" export * }
  module "RooExtendedBinding.h" { header "RooExtendedBinding.h" export * }
  module "RooExtendedTerm.h" { header "RooExtendedTerm.h" export * }
  module "RooFFTConvPdf.h" { header "RooFFTConvPdf.h" export * }
  module "RooFactoryWSTool.h" { header "RooFactoryWSTool.h" export * }
  module "RooFirstMoment.h" { header "RooFirstMoment.h" export * }
  module "RooFit.h" { header "RooFit.h" export * }
  module "RooFit/CodegenContext.h" { header "RooFit/CodegenContext.h" export * }
  module "RooFit/Config.h" { header "RooFit/Config.h" export * }
  module "RooFit/Detail/MathFuncs.h" { header "RooFit/Detail/MathFuncs.h" export * }
  module "RooFit/Detail/NormalizationHelpers.h" { header "RooFit/Detail/NormalizationHelpers.h" export * }
  module "RooFit/Detail/RooNLLVarNew.h" { header "RooFit/Detail/RooNLLVarNew.h" export * }
  module "RooFit/Detail/RooNormalizedPdf.h" { header "RooFit/Detail/RooNormalizedPdf.h" export * }
  module "RooFit/EvalContext.h" { header "RooFit/EvalContext.h" export * }
  module "RooFit/Evaluator.h" { header "RooFit/Evaluator.h" export * }
  module "RooFit/Floats.h" { header "RooFit/Floats.h" export * }
  module "RooFit/ModelConfig.h" { header "RooFit/ModelConfig.h" export * }
  module "RooFit/TestStatistics/LikelihoodGradientWrapper.h" { header "RooFit/TestStatistics/LikelihoodGradientWrapper.h" export * }
  module "RooFit/TestStatistics/LikelihoodWrapper.h" { header "RooFit/TestStatistics/LikelihoodWrapper.h" export * }
  module "RooFit/TestStatistics/RooAbsL.h" { header "RooFit/TestStatistics/RooAbsL.h" export * }
  module "RooFit/TestStatistics/RooBinnedL.h" { header "RooFit/TestStatistics/RooBinnedL.h" export * }
  module "RooFit/TestStatistics/RooRealL.h" { header "RooFit/TestStatistics/RooRealL.h" export * }
  module "RooFit/TestStatistics/RooSubsidiaryL.h" { header "RooFit/TestStatistics/RooSubsidiaryL.h" export * }
  module "RooFit/TestStatistics/RooSumL.h" { header "RooFit/TestStatistics/RooSumL.h" export * }
  module "RooFit/TestStatistics/RooUnbinnedL.h" { header "RooFit/TestStatistics/RooUnbinnedL.h" export * }
  module "RooFit/TestStatistics/SharedOffset.h" { header "RooFit/TestStatistics/SharedOffset.h" export * }
  module "RooFit/TestStatistics/buildLikelihood.h" { header "RooFit/TestStatistics/buildLikelihood.h" export * }
  module "RooFitLegacy/RooCatTypeLegacy.h" { header "RooFitLegacy/RooCatTypeLegacy.h" export * }
  module "RooFitLegacy/RooCategorySharedProperties.h" { header "RooFitLegacy/RooCategorySharedProperties.h" export * }
  module "RooFitLegacy/RooTreeData.h" { header "RooFitLegacy/RooTreeData.h" export * }
  module "RooFitResult.h" { header "RooFitResult.h" export * }
  module "RooFormulaVar.h" { header "RooFormulaVar.h" export * }
  module "RooFracRemainder.h" { header "RooFracRemainder.h" export * }
  module "RooFunctor.h" { header "RooFunctor.h" export * }
  module "RooGenContext.h" { header "RooGenContext.h" export * }
  module "RooGenFitStudy.h" { header "RooGenFitStudy.h" export * }
  module "RooGenericPdf.h" { header "RooGenericPdf.h" export * }
  module "RooGlobalFunc.h" { header "RooGlobalFunc.h" export * }
  module "RooHelpers.h" { header "RooHelpers.h" export * }
  module "RooHist.h" { header "RooHist.h" export * }
  module "RooHistError.h" { header "RooHistError.h" export * }
  module "RooHistFunc.h" { header "RooHistFunc.h" export * }
  module "RooHistPdf.h" { header "RooHistPdf.h" export * }
  module "RooInvTransform.h" { header "RooInvTransform.h" export * }
  module "RooLinTransBinning.h" { header "RooLinTransBinning.h" export * }
  module "RooLinearCombination.h" { header "RooLinearCombination.h" export * }
  module "RooLinearVar.h" { header "RooLinearVar.h" export * }
  module "RooLinkedList.h" { header "RooLinkedList.h" export * }
  module "RooLinkedListElem.h" { header "RooLinkedListElem.h" export * }
  module "RooLinkedListIter.h" { header "RooLinkedListIter.h" export * }
  module "RooListProxy.h" { header "RooListProxy.h" export * }
  module "RooMCStudy.h" { header "RooMCStudy.h" export * }
  module "RooMappedCategory.h" { header "RooMappedCategory.h" export * }
  module "RooMath.h" { header "RooMath.h" export * }
  module "RooMinimizer.h" { header "RooMinimizer.h" export * }
  module "RooMoment.h" { header "RooMoment.h" export * }
  module "RooMsgService.h" { header "RooMsgService.h" export * }
  module "RooMultiCategory.h" { header "RooMultiCategory.h" export * }
  module "RooMultiPdf.h" { header "RooMultiPdf.h" export * }
  module "RooMultiReal.h" { header "RooMultiReal.h" export * }
  module "RooMultiVarGaussian.h" { header "RooMultiVarGaussian.h" export * }
  module "RooNameReg.h" { header "RooNameReg.h" export * }
  module "RooNormSetCache.h" { header "RooNormSetCache.h" export * }
  module "RooNumCdf.h" { header "RooNumCdf.h" export * }
  module "RooNumConvPdf.h" { header "RooNumConvPdf.h" export * }
  module "RooNumConvolution.h" { header "RooNumConvolution.h" export * }
  module "RooNumGenConfig.h" { header "RooNumGenConfig.h" export * }
  module "RooNumIntConfig.h" { header "RooNumIntConfig.h" export * }
  module "RooNumIntFactory.h" { header "RooNumIntFactory.h" export * }
  module "RooNumRunningInt.h" { header "RooNumRunningInt.h" export * }
  module "RooNumber.h" { header "RooNumber.h" export * }
  module "RooObjCacheManager.h" { header "RooObjCacheManager.h" export * }
  module "RooParamBinning.h" { header "RooParamBinning.h" export * }
  module "RooPlot.h" { header "RooPlot.h" export * }
  module "RooPlotable.h" { header "RooPlotable.h" export * }
  module "RooPolyFunc.h" { header "RooPolyFunc.h" export * }
  module "RooPolyVar.h" { header "RooPolyVar.h" export * }
  module "RooPrintable.h" { header "RooPrintable.h" export * }
  module "RooProdGenContext.h" { header "RooProdGenContext.h" export * }
  module "RooProdPdf.h" { header "RooProdPdf.h" export * }
  module "RooProduct.h" { header "RooProduct.h" export * }
  module "RooProfileLL.h" { header "RooProfileLL.h" export * }
  module "RooProjectedPdf.h" { header "RooProjectedPdf.h" export * }
  module "RooPullVar.h" { header "RooPullVar.h" export * }
  module "RooQuasiRandomGenerator.h" { header "RooQuasiRandomGenerator.h" export * }
  module "RooRandom.h" { header "RooRandom.h" export * }
  module "RooRandomizeParamMCSModule.h" { header "RooRandomizeParamMCSModule.h" export * }
  module "RooRangeBinning.h" { header "RooRangeBinning.h" export * }
  module "RooRangeBoolean.h" { header "RooRangeBoolean.h" export * }
  module "RooRatio.h" { header "RooRatio.h" export * }
  module "RooRealBinding.h" { header "RooRealBinding.h" export * }
  module "RooRealConstant.h" { header "RooRealConstant.h" export * }
  module "RooRealIntegral.h" { header "RooRealIntegral.h" export * }
  module "RooRealProxy.h" { header "RooRealProxy.h" export * }
  module "RooRealSumFunc.h" { header "RooRealSumFunc.h" export * }
  module "RooRealSumPdf.h" { header "RooRealSumPdf.h" export * }
  module "RooRealVar.h" { header "RooRealVar.h" export * }
  module "RooRealVarSharedProperties.h" { header "RooRealVarSharedProperties.h" export * }
  module "RooRecursiveFraction.h" { header "RooRecursiveFraction.h" export * }
  module "RooRefCountList.h" { header "RooRefCountList.h" export * }
  module "RooResolutionModel.h" { header "RooResolutionModel.h" export * }
  module "RooSTLRefCountList.h" { header "RooSTLRefCountList.h" export * }
  module "RooSecondMoment.h" { header "RooSecondMoment.h" export * }
  module "RooSetProxy.h" { header "RooSetProxy.h" export * }
  module "RooSharedProperties.h" { header "RooSharedProperties.h" export * }
  module "RooSimGenContext.h" { header "RooSimGenContext.h" export * }
  module "RooSimSplitGenContext.h" { header "RooSimSplitGenContext.h" export * }
  module "RooSimWSTool.h" { header "RooSimWSTool.h" export * }
  module "RooSimultaneous.h" { header "RooSimultaneous.h" export * }
  module "RooStreamParser.h" { header "RooStreamParser.h" export * }
  module "RooStringVar.h" { header "RooStringVar.h" export * }
  module "RooStringView.h" { header "RooStringView.h" export * }
  module "RooStudyManager.h" { header "RooStudyManager.h" export * }
  module "RooStudyPackage.h" { header "RooStudyPackage.h" export * }
  module "RooSuperCategory.h" { header "RooSuperCategory.h" export * }
  module "RooTObjWrap.h" { header "RooTObjWrap.h" export * }
  module "RooTable.h" { header "RooTable.h" export * }
  module "RooTemplateProxy.h" { header "RooTemplateProxy.h" export * }
  module "RooThresholdCategory.h" { header "RooThresholdCategory.h" export * }
  module "RooTrace.h" { header "RooTrace.h" export * }
  module "RooTreeDataStore.h" { header "RooTreeDataStore.h" export * }
  module "RooTruthModel.h" { header "RooTruthModel.h" export * }
  module "RooUniformBinning.h" { header "RooUniformBinning.h" export * }
  module "RooVectorDataStore.h" { header "RooVectorDataStore.h" export * }
  module "RooWorkspace.h" { header "RooWorkspace.h" export * }
  module "RooWorkspaceHandle.h" { header "RooWorkspaceHandle.h" export * }
  module "RooWrapperPdf.h" { header "RooWrapperPdf.h" export * }
  link "libRooFitCore.so"
  export *
}
 
module "RooFit" {
  requires cplusplus
  module "Roo2DKeysPdf.h" { header "Roo2DKeysPdf.h" export * }
  module "RooArgusBG.h" { header "RooArgusBG.h" export * }
  module "RooBCPEffDecay.h" { header "RooBCPEffDecay.h" export * }
  module "RooBCPGenDecay.h" { header "RooBCPGenDecay.h" export * }
  module "RooBDecay.h" { header "RooBDecay.h" export * }
  module "RooBMixDecay.h" { header "RooBMixDecay.h" export * }
  module "RooBernstein.h" { header "RooBernstein.h" export * }
  module "RooBifurGauss.h" { header "RooBifurGauss.h" export * }
  module "RooBlindTools.h" { header "RooBlindTools.h" export * }
  module "RooBreitWigner.h" { header "RooBreitWigner.h" export * }
  module "RooBukinPdf.h" { header "RooBukinPdf.h" export * }
  module "RooCBShape.h" { header "RooCBShape.h" export * }
  module "RooCFunction1Binding.h" { header "RooCFunction1Binding.h" export * }
  module "RooCFunction2Binding.h" { header "RooCFunction2Binding.h" export * }
  module "RooCFunction3Binding.h" { header "RooCFunction3Binding.h" export * }
  module "RooCFunction4Binding.h" { header "RooCFunction4Binding.h" export * }
  module "RooChebychev.h" { header "RooChebychev.h" export * }
  module "RooChi2MCSModule.h" { header "RooChi2MCSModule.h" export * }
  module "RooChiSquarePdf.h" { header "RooChiSquarePdf.h" export * }
  module "RooCrystalBall.h" { header "RooCrystalBall.h" export * }
  module "RooDecay.h" { header "RooDecay.h" export * }
  module "RooDstD0BG.h" { header "RooDstD0BG.h" export * }
  module "RooExponential.h" { header "RooExponential.h" export * }
  module "RooFunctor1DBinding.h" { header "RooFunctor1DBinding.h" export * }
  module "RooFunctorBinding.h" { header "RooFunctorBinding.h" export * }
  module "RooGExpModel.h" { header "RooGExpModel.h" export * }
  module "RooGamma.h" { header "RooGamma.h" export * }
  module "RooGaussExpTails.h" { header "RooGaussExpTails.h" export * }
  module "RooGaussModel.h" { header "RooGaussModel.h" export * }
  module "RooGaussian.h" { header "RooGaussian.h" export * }
  module "RooHistConstraint.h" { header "RooHistConstraint.h" export * }
  module "RooIntegralMorph.h" { header "RooIntegralMorph.h" export * }
  module "RooJeffreysPrior.h" { header "RooJeffreysPrior.h" export * }
  module "RooJohnson.h" { header "RooJohnson.h" export * }
  module "RooKeysPdf.h" { header "RooKeysPdf.h" export * }
  module "RooLagrangianMorphFunc.h" { header "RooLagrangianMorphFunc.h" export * }
  module "RooLandau.h" { header "RooLandau.h" export * }
  module "RooLegacyExpPoly.h" { header "RooLegacyExpPoly.h" export * }
  module "RooLognormal.h" { header "RooLognormal.h" export * }
  module "RooMathCoreReg.h" { header "RooMathCoreReg.h" export * }
  module "RooMomentMorph.h" { header "RooMomentMorph.h" export * }
  module "RooMomentMorphFunc.h" { header "RooMomentMorphFunc.h" export * }
  module "RooMomentMorphFuncND.h" { header "RooMomentMorphFuncND.h" export * }
  module "RooMultiBinomial.h" { header "RooMultiBinomial.h" export * }
  module "RooNDKeysPdf.h" { header "RooNDKeysPdf.h" export * }
  module "RooNonCPEigenDecay.h" { header "RooNonCPEigenDecay.h" export * }
  module "RooNovosibirsk.h" { header "RooNovosibirsk.h" export * }
  module "RooONNXFunc.h" { header "RooONNXFunc.h" export * }
  module "RooParamHistFunc.h" { header "RooParamHistFunc.h" export * }
  module "RooParametricStepFunction.h" { header "RooParametricStepFunction.h" export * }
  module "RooPoisson.h" { header "RooPoisson.h" export * }
  module "RooPolynomial.h" { header "RooPolynomial.h" export * }
  module "RooPowerSum.h" { header "RooPowerSum.h" export * }
  module "RooPyBind.h" { header "RooPyBind.h" export * }
  module "RooSpline.h" { header "RooSpline.h" export * }
  module "RooStepFunction.h" { header "RooStepFunction.h" export * }
  module "RooStudentT.h" { header "RooStudentT.h" export * }
  module "RooTFnBinding.h" { header "RooTFnBinding.h" export * }
  module "RooTFnPdfBinding.h" { header "RooTFnPdfBinding.h" export * }
  module "RooTMathReg.h" { header "RooTMathReg.h" export * }
  module "RooUnblindCPAsymVar.h" { header "RooUnblindCPAsymVar.h" export * }
  module "RooUnblindOffset.h" { header "RooUnblindOffset.h" export * }
  module "RooUnblindPrecision.h" { header "RooUnblindPrecision.h" export * }
  module "RooUnblindUniform.h" { header "RooUnblindUniform.h" export * }
  module "RooUniform.h" { header "RooUniform.h" export * }
  module "RooVoigtian.h" { header "RooVoigtian.h" export * }
  link "libRooFit.so"
  export *
}
 
module "RooFitMore" {
  requires cplusplus
  module "RooFitMoreLib.h" { header "RooFitMoreLib.h" export * }
  module "RooLegendre.h" { header "RooLegendre.h" export * }
  module "RooMathMoreReg.h" { header "RooMathMoreReg.h" export * }
  module "RooSpHarmonic.h" { header "RooSpHarmonic.h" export * }
  module "RooNonCentralChiSquare.h" { header "RooNonCentralChiSquare.h" export * }
  module "RooHypatia2.h" { header "RooHypatia2.h" export * }
  link "libRooFitMore.so"
  export *
}
 
module "RooStats" {
  requires cplusplus
  module "RooStats/AsymptoticCalculator.h" { header "RooStats/AsymptoticCalculator.h" export * }
  module "RooStats/BayesianCalculator.h" { header "RooStats/BayesianCalculator.h" export * }
  module "RooStats/BernsteinCorrection.h" { header "RooStats/BernsteinCorrection.h" export * }
  module "RooStats/CombinedCalculator.h" { header "RooStats/CombinedCalculator.h" export * }
  module "RooStats/ConfidenceBelt.h" { header "RooStats/ConfidenceBelt.h" export * }
  module "RooStats/ConfInterval.h" { header "RooStats/ConfInterval.h" export * }
  module "RooStats/DebuggingSampler.h" { header "RooStats/DebuggingSampler.h" export * }
  module "RooStats/DebuggingTestStat.h" { header "RooStats/DebuggingTestStat.h" export * }
  module "RooStats/DetailedOutputAggregator.h" { header "RooStats/DetailedOutputAggregator.h" export * }
  module "RooStats/FeldmanCousins.h" { header "RooStats/FeldmanCousins.h" export * }
  module "RooStats/FrequentistCalculator.h" { header "RooStats/FrequentistCalculator.h" export * }
  module "RooStats/Heaviside.h" { header "RooStats/Heaviside.h" export * }
  module "RooStats/HybridCalculator.h" { header "RooStats/HybridCalculator.h" export * }
  module "RooStats/HybridResult.h" { header "RooStats/HybridResult.h" export * }
  module "RooStats/HypoTestCalculatorGeneric.h" { header "RooStats/HypoTestCalculatorGeneric.h" export * }
  module "RooStats/HypoTestCalculator.h" { header "RooStats/HypoTestCalculator.h" export * }
  module "RooStats/HypoTestInverter.h" { header "RooStats/HypoTestInverter.h" export * }
  module "RooStats/HypoTestInverterPlot.h" { header "RooStats/HypoTestInverterPlot.h" export * }
  module "RooStats/HypoTestInverterResult.h" { header "RooStats/HypoTestInverterResult.h" export * }
  module "RooStats/HypoTestPlot.h" { header "RooStats/HypoTestPlot.h" export * }
  module "RooStats/HypoTestResult.h" { header "RooStats/HypoTestResult.h" export * }
  module "RooStats/IntervalCalculator.h" { header "RooStats/IntervalCalculator.h" export * }
  module "RooStats/LikelihoodInterval.h" { header "RooStats/LikelihoodInterval.h" export * }
  module "RooStats/LikelihoodIntervalPlot.h" { header "RooStats/LikelihoodIntervalPlot.h" export * }
  module "RooStats/MarkovChain.h" { header "RooStats/MarkovChain.h" export * }
  module "RooStats/MaxLikelihoodEstimateTestStat.h" { header "RooStats/MaxLikelihoodEstimateTestStat.h" export * }
  module "RooStats/MCMCCalculator.h" { header "RooStats/MCMCCalculator.h" export * }
  module "RooStats/MCMCInterval.h" { header "RooStats/MCMCInterval.h" export * }
  module "RooStats/MCMCIntervalPlot.h" { header "RooStats/MCMCIntervalPlot.h" export * }
  module "RooStats/MetropolisHastings.h" { header "RooStats/MetropolisHastings.h" export * }
  module "RooStats/ModelConfig.h" { header "RooStats/ModelConfig.h" export * }
  module "RooStats/NeymanConstruction.h" { header "RooStats/NeymanConstruction.h" export * }
  module "RooStats/NumberCountingPdfFactory.h" { header "RooStats/NumberCountingPdfFactory.h" export * }
  module "RooStats/NumberCountingUtils.h" { header "RooStats/NumberCountingUtils.h" export * }
  module "RooStats/NumEventsTestStat.h" { header "RooStats/NumEventsTestStat.h" export * }
  module "RooStats/PdfProposal.h" { header "RooStats/PdfProposal.h" export * }
  module "RooStats/PointSetInterval.h" { header "RooStats/PointSetInterval.h" export * }
  module "RooStats/ProfileInspector.h" { header "RooStats/ProfileInspector.h" export * }
  module "RooStats/ProfileLikelihoodCalculator.h" { header "RooStats/ProfileLikelihoodCalculator.h" export * }
  module "RooStats/ProfileLikelihoodTestStat.h" { header "RooStats/ProfileLikelihoodTestStat.h" export * }
  module "RooStats/ProposalFunction.h" { header "RooStats/ProposalFunction.h" export * }
  module "RooStats/ProposalHelper.h" { header "RooStats/ProposalHelper.h" export * }
  module "RooStats/RatioOfProfiledLikelihoodsTestStat.h" { header "RooStats/RatioOfProfiledLikelihoodsTestStat.h" export * }
  module "RooStats/RooStatsUtils.h" { header "RooStats/RooStatsUtils.h" export * }
  module "RooStats/SamplingDistPlot.h" { header "RooStats/SamplingDistPlot.h" export * }
  module "RooStats/SamplingDistribution.h" { header "RooStats/SamplingDistribution.h" export * }
  module "RooStats/SequentialProposal.h" { header "RooStats/SequentialProposal.h" export * }
  module "RooStats/SimpleInterval.h" { header "RooStats/SimpleInterval.h" export * }
  module "RooStats/SimpleLikelihoodRatioTestStat.h" { header "RooStats/SimpleLikelihoodRatioTestStat.h" export * }
  module "RooStats/SPlot.h" { header "RooStats/SPlot.h" export * }
  module "RooStats/TestStatistic.h" { header "RooStats/TestStatistic.h" export * }
  module "RooStats/TestStatSampler.h" { header "RooStats/TestStatSampler.h" export * }
  module "RooStats/ToyMCImportanceSampler.h" { header "RooStats/ToyMCImportanceSampler.h" export * }
  module "RooStats/ToyMCSampler.h" { header "RooStats/ToyMCSampler.h" export * }
  module "RooStats/UniformProposal.h" { header "RooStats/UniformProposal.h" export * }
  module "RooStats/UpperLimitMCSModule.h" { header "RooStats/UpperLimitMCSModule.h" export * }
  link "libRooStats.so"
  export *
}
 
module "HistFactory" {
  requires cplusplus
  module "RooStats/HistFactory/Detail/HistFactoryImpl.h" { header "RooStats/HistFactory/Detail/HistFactoryImpl.h" export * }
  module "RooStats/HistFactory/FlexibleInterpVar.h" { header "RooStats/HistFactory/FlexibleInterpVar.h" export * }
  module "RooStats/HistFactory/HistFactoryException.h" { header "RooStats/HistFactory/HistFactoryException.h" export * }
  module "RooStats/HistFactory/HistFactoryModelUtils.h" { header "RooStats/HistFactory/HistFactoryModelUtils.h" export * }
  module "RooStats/HistFactory/HistFactoryNavigation.h" { header "RooStats/HistFactory/HistFactoryNavigation.h" export * }
  module "RooStats/HistFactory/HistoToWorkspaceFactoryFast.h" { header "RooStats/HistFactory/HistoToWorkspaceFactoryFast.h" export * }
  module "RooStats/HistFactory/LinInterpVar.h" { header "RooStats/HistFactory/LinInterpVar.h" export * }
  module "RooStats/HistFactory/MakeModelAndMeasurementsFast.h" { header "RooStats/HistFactory/MakeModelAndMeasurementsFast.h" export * }
  module "RooStats/HistFactory/Measurement.h" { header "RooStats/HistFactory/Measurement.h" export * }
  module "RooStats/HistFactory/ParamHistFunc.h" { header "RooStats/HistFactory/ParamHistFunc.h" export * }
  module "RooStats/HistFactory/PiecewiseInterpolation.h" { header "RooStats/HistFactory/PiecewiseInterpolation.h" export * }
  module "RooStats/HistFactory/RooBarlowBeestonLL.h" { header "RooStats/HistFactory/RooBarlowBeestonLL.h" export * }
  link "libHistFactory.so"
  export *
}
 
module "RooFitJSONInterface" {
  requires cplusplus
  module "RooFit/Detail/JSONInterface.h" { header "RooFit/Detail/JSONInterface.h" export * }
  link "libRooFitJSONInterface.so"
  export *
}
 
module "RooFitHS3" {
  requires cplusplus
  module "RooFitHS3/JSONIO.h" { header "RooFitHS3/JSONIO.h" export * }
  module "RooFitHS3/RooJSONFactoryWSTool.h" { header "RooFitHS3/RooJSONFactoryWSTool.h" export * }
  link "libRooFitHS3.so"
  export *
}
 
module "RooFitXRooFit" {
  requires cplusplus
  module "RooBrowser.h" { header "RooBrowser.h" export * }
  module "XRooFit.h" { header "XRooFit.h" export * }
  module "RooFit/xRooFit/xRooFit.h" { header "RooFit/xRooFit/xRooFit.h" export * }
  module "RooFit/xRooFit/xRooNode.h" { header "RooFit/xRooFit/xRooNode.h" export * }
  module "RooFit/xRooFit/xRooNLLVar.h" { header "RooFit/xRooFit/xRooNLLVar.h" export * }
  module "RooFit/xRooFit/xRooHypoSpace.h" { header "RooFit/xRooFit/xRooHypoSpace.h" export * }
  module "RooFit/xRooFit/xRooBrowser.h" { header "RooFit/xRooFit/xRooBrowser.h" export * }
  link "libRooFitXRooFit.so"
  export *
}''',
}

if __name__ == "__main__":
    bootstrap()

