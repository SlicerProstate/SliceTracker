import os
import vtk, qt, slicer
from slicer.ScriptedLoadableModule import *
from SliceTrackerUtils.mixins import ModuleLogicMixin, ModuleWidgetMixin
from SliceTrackerUtils.RegistrationData import RegistrationResult
import argparse
import sys
import logging


class SliceTrackerRegistration(ScriptedLoadableModule):

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "SliceTracker Registration"
    self.parent.categories = ["Radiology"]
    self.parent.dependencies = []
    self.parent.contributors = ["Peter Behringer (SPL), Christian Herz (SPL), Andriy Fedorov (SPL)"]
    self.parent.helpText = """ SliceTracker Registration facilitates support of MRI-guided targeted prostate biopsy. """
    self.parent.acknowledgementText = """Surgical Planning Laboratory, Brigham and Women's Hospital, Harvard
                                          Medical School, Boston, USA This work was supported in part by the National
                                          Institutes of Health through grants U24 CA180918,
                                          R01 CA111288 and P41 EB015898."""
    self.parent = parent

    try:
      slicer.selfTests
    except AttributeError:
      slicer.selfTests = {}
    slicer.selfTests['SliceTrackerRegistration'] = self.runTest

  def runTest(self):
    tester = SliceTrackerRegistration()
    tester.runTest()


class SliceTrackerRegistrationWidget(ScriptedLoadableModuleWidget, ModuleWidgetMixin):

  def __init__(self, parent=None):
    ScriptedLoadableModuleWidget.__init__(self, parent)
    self.logic = SliceTrackerRegistrationLogic()

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)
    self.registrationGroupBox = qt.QGroupBox()
    self.registrationGroupBoxLayout = qt.QFormLayout()
    self.registrationGroupBox.setLayout(self.registrationGroupBoxLayout)
    self.preopVolumeSelector = self.createComboBox(nodeTypes=["vtkMRMLScalarVolumeNode", ""], showChildNodeTypes=False,
                                                   selectNodeUponCreation=True, toolTip="Pick algorithm input.")
    self.preopLabelSelector = self.createComboBox(nodeTypes=["vtkMRMLLabelMapVolumeNode", ""], showChildNodeTypes=False,
                                                  selectNodeUponCreation=False, toolTip="Pick algorithm input.")
    self.intraopVolumeSelector = self.createComboBox(nodeTypes=["vtkMRMLScalarVolumeNode", ""], noneEnabled=True,
                                                     showChildNodeTypes=False, selectNodeUponCreation=True,
                                                     toolTip="Pick algorithm input.")
    self.intraopLabelSelector = self.createComboBox(nodeTypes=["vtkMRMLLabelMapVolumeNode", ""],
                                                    showChildNodeTypes=False,
                                                    selectNodeUponCreation=True, toolTip="Pick algorithm input.")
    self.fiducialSelector = self.createComboBox(nodeTypes=["vtkMRMLMarkupsFiducialNode", ""], noneEnabled=True,
                                                showChildNodeTypes=False, selectNodeUponCreation=False,
                                                toolTip="Select the Targets")
    self.applyRegistrationButton = self.createButton("Run Registration")
    self.registrationGroupBoxLayout.addRow("Preop Image Volume: ", self.preopVolumeSelector)
    self.registrationGroupBoxLayout.addRow("Preop Label Volume: ", self.preopLabelSelector)
    self.registrationGroupBoxLayout.addRow("Intraop Image Volume: ", self.intraopVolumeSelector)
    self.registrationGroupBoxLayout.addRow("Intraop Label Volume: ", self.intraopLabelSelector)
    self.registrationGroupBoxLayout.addRow("Targets: ", self.fiducialSelector)
    self.registrationGroupBoxLayout.addRow(self.applyRegistrationButton)
    self.layout.addWidget(self.registrationGroupBox)
    self.layout.addStretch()
    self.applyRegistrationButton.clicked.connect(self.runRegistration)

  def runRegistration(self):
    self.progress = self.makeProgressIndicator(4, 1)
    self.logic.runRegistration(fixedVolume=self.intraopVolumeSelector.currentNode(),
                               movingVolume=self.preopVolumeSelector.currentNode(),
                               fixedLabel=self.intraopLabelSelector.currentNode(),
                               movingLabel=self.preopLabelSelector.currentNode(),
                               targets=self.fiducialSelector.currentNode(),
                               progressCallback=self.updateProgressBar)
    self.progress.close()

  def updateProgressBar(self, **kwargs):
    if self.progress:
      for key, value in kwargs.iteritems():
        if hasattr(self.progress, key):
          setattr(self.progress, key, value)


class SliceTrackerRegistrationLogic(ScriptedLoadableModuleLogic, ModuleLogicMixin):

  def __init__(self):
    ScriptedLoadableModuleLogic.__init__(self)
    self.volumesLogic = slicer.modules.volumes.logic()
    self.markupsLogic = slicer.modules.markups.logic()
    self.registrationResult = None

  def runRegistration(self, fixedVolume, movingVolume, fixedLabel, movingLabel, targets=None, progressCallback=None):

    self.progressCallback = progressCallback
    registrationTypes = ['rigid', 'affine', 'bSpline']

    if not self.registrationResult:
      self.registrationResult = RegistrationResult("01: RegistrationResult")
    result = self.registrationResult
    result.fixedVolume = fixedVolume
    result.fixedLabel = fixedLabel
    result.movingLabel = movingLabel
    result.movingVolume = self.volumesLogic.CloneVolume(slicer.mrmlScene, movingVolume, "temp-movingVolume")

    self.createVolumeAndTransformNodes(registrationTypes, prefix=str(result.seriesNumber), suffix=result.suffix)

    self.doRigidRegistration(movingBinaryVolume=result.movingLabel, initializeTransformMode="useCenterOfROIAlign")
    self.doAffineRegistration()
    self.doBSplineRegistration(initialTransform=result.affineTransform)

    if targets:
      result.originalTargets = targets
      self.transformTargets(registrationTypes, result.originalTargets, str(result.seriesNumber))
    result.movingVolume = movingVolume

  def runReRegistration(self, fixedVolume, movingVolume, fixedLabel, movingLabel, targets=None, initialTransform=None,
                       progressCallback=None):
    self.progressCallback = progressCallback
    registrationTypes = ['rigid', 'bSpline']

    if not self.registrationResult:
      self.registrationResult = RegistrationResult("01: RegistrationResult")
    result = self.registrationResult
    result.fixedVolume = fixedVolume
    result.fixedLabel = self.volumesLogic.CreateAndAddLabelVolume(slicer.mrmlScene, fixedVolume,
                                                                  fixedVolume.GetName() + '-label')
    result.movingLabel = movingLabel
    result.movingVolume = self.volumesLogic.CloneVolume(slicer.mrmlScene, movingVolume, "temp-movingVolume")

    self.createVolumeAndTransformNodes(registrationTypes, prefix=str(result.seriesNumber), suffix=result.suffix)

    self.runBRAINSResample(inputVolume=fixedLabel, referenceVolume=fixedVolume, outputVolume=result.fixedLabel,
                           warpTransform=initialTransform)
    if initialTransform:
      self.doRigidRegistration(movingBinaryVolume=result.movingLabel, initialTransform=initialTransform)
    else:
      self.doRigidRegistration(movingBinaryVolume=result.movingLabel)

    self.dilateMask(result.fixedLabel)
    self.doBSplineRegistration(initialTransform=result.rigidTransform, useScaleVersor3D=True,
                             useScaleSkewVersor3D=True, useAffine=True)

    if targets:
      result.originalTargets = targets
      self.transformTargets(registrationTypes, result.originalTargets, str(result.seriesNumber))
    result.movingVolume = movingVolume

  def dilateMask(self, mask):
    imagedata = mask.GetImageData()
    dilateErode = vtk.vtkImageDilateErode3D()
    dilateErode.SetInputData(imagedata)
    dilateErode.SetDilateValue(1.0)
    dilateErode.SetErodeValue(0.0)
    dilateErode.SetKernelSize(12,12,1)
    dilateErode.Update()
    mask.SetAndObserveImageData(dilateErode.GetOutput())

  def runBRAINSResample(self, inputVolume, referenceVolume, outputVolume, warpTransform):

    params = {'inputVolume': inputVolume, 'referenceVolume': referenceVolume, 'outputVolume': outputVolume,
              'interpolationMode': 'NearestNeighbor'}
    if warpTransform:
      params['warpTransform'] = warpTransform,

    logging.debug('about to run BRAINSResample CLI with those params: ')
    logging.debug(params)
    slicer.cli.run(slicer.modules.brainsresample, None, params, wait_for_completion=True)
    logging.debug('resample labelmap through')
    slicer.mrmlScene.AddNode(outputVolume)

  def createVolumeAndTransformNodes(self, registrationTypes, prefix, suffix=""):
    for regType in registrationTypes:
      self.registrationResult.setVolume(regType, self.createScalarVolumeNode(prefix + '-VOLUME-' + regType + suffix))
      transformName = prefix + '-TRANSFORM-' + regType + suffix
      transform = self.createBSplineTransformNode(transformName) if regType == 'bSpline' \
        else self.createLinearTransformNode(transformName)
      self.registrationResult.setTransform(regType, transform)

  def transformTargets(self, registrations, targets, prefix):
    if targets:
      for registration in registrations:
        name = prefix + '-TARGETS-' + registration
        clone = self.cloneFiducialAndTransform(name, targets, self.registrationResult.getTransform(registration))
        self.markupsLogic.SetAllMarkupsLocked(clone, True)
        self.registrationResult.setTargets(registration, clone)

  def cloneFiducialAndTransform(self, cloneName, originalTargets, transformNode):
    tfmLogic = slicer.modules.transforms.logic()
    clonedTargets = self.cloneFiducials(originalTargets, cloneName)
    clonedTargets.SetAndObserveTransformNodeID(transformNode.GetID())
    tfmLogic.hardenTransform(clonedTargets)
    return clonedTargets

  def cloneFiducials(self, original, cloneName):
    nodeId = self.markupsLogic.AddNewFiducialNode(cloneName, slicer.mrmlScene)
    clone = slicer.mrmlScene.GetNodeByID(nodeId)
    for i in range(original.GetNumberOfFiducials()):
      pos = [0.0, 0.0, 0.0]
      original.GetNthFiducialPosition(i, pos)
      name = original.GetNthFiducialLabel(i)
      clone.AddFiducial(pos[0], pos[1], pos[2])
      clone.SetNthFiducialLabel(i, name)
    return clone

  def doRigidRegistration(self, **kwargs):
    self.updateProgress(labelText='\nRigid registration', value=2)
    paramsRigid = {'fixedVolume': self.registrationResult.fixedVolume,
                   'movingVolume': self.registrationResult.movingVolume,
                   'fixedBinaryVolume': self.registrationResult.fixedLabel,
                   'outputTransform': self.registrationResult.rigidTransform.GetID(),
                   'outputVolume': self.registrationResult.rigidVolume.GetID(),
                   'maskProcessingMode': "ROI",
                   'useRigid': True}
    for key, value in kwargs.iteritems():
      paramsRigid[key] = value
    slicer.cli.run(slicer.modules.brainsfit, None, paramsRigid, wait_for_completion=True)
    self.registrationResult.cmdArguments += "Rigid Registration Parameters: %s" % str(paramsRigid) + "\n\n"

  def doAffineRegistration(self):
    self.updateProgress(labelText='\nAffine registration', value=2)
    paramsAffine = {'fixedVolume': self.registrationResult.fixedVolume,
                    'movingVolume': self.registrationResult.movingVolume,
                    'fixedBinaryVolume': self.registrationResult.fixedLabel,
                    'movingBinaryVolume': self.registrationResult.movingLabel,
                    'outputTransform': self.registrationResult.affineTransform.GetID(),
                    'outputVolume': self.registrationResult.affineVolume.GetID(),
                    'maskProcessingMode': "ROI",
                    'useAffine': True,
                    'initialTransform': self.registrationResult.rigidTransform}
    slicer.cli.run(slicer.modules.brainsfit, None, paramsAffine, wait_for_completion=True)
    self.registrationResult.cmdArguments += "Affine Registration Parameters: %s" % str(paramsAffine) + "\n\n"

  def doBSplineRegistration(self, initialTransform, **kwargs):
    self.updateProgress(labelText='\nBSpline registration', value=3)
    paramsBSpline = {'fixedVolume': self.registrationResult.fixedVolume,
                     'movingVolume': self.registrationResult.movingVolume,
                     'outputVolume': self.registrationResult.bSplineVolume.GetID(),
                     'bsplineTransform': self.registrationResult.bSplineTransform.GetID(),
                     'fixedBinaryVolume': self.registrationResult.fixedLabel,
                     'movingBinaryVolume': self.registrationResult.movingLabel,
                     'useROIBSpline': True,
                     'useBSpline': True,
                     'splineGridSize': "3,3,3",
                     'maskProcessing': "ROI",
                     'minimumStepLength': "0.005",
                     'maximumStepLength': "0.2",
                     'costFunctionConvergenceFactor': "1.00E+09",
                     'maskProcessingMode': "ROI",
                     'initialTransform': initialTransform}
    for key, value in kwargs.iteritems():
      paramsBSpline[key] = value

    slicer.cli.run(slicer.modules.brainsfit, None, paramsBSpline, wait_for_completion=True)
    self.registrationResult.cmdArguments += "BSpline Registration Parameters: %s" % str(paramsBSpline) + "\n\n"

    self.updateProgress(labelText='\nCompleted registration', value=4)

  def updateProgress(self, **kwargs):
    if self.progressCallback:
      self.progressCallback(**kwargs)


def main(argv):
  try:
    parser = argparse.ArgumentParser(description="Slicetracker Registration")
    parser.add_argument("-fl", "--fixed-label", dest="fixed_label", metavar="PATH", default="-", required=True,
                        help="Fixed label to be used for registration")
    parser.add_argument("-ml", "--moving-label", dest="moving_label", metavar="PATH", default="-", required=True,
                        help="Moving label to be used for registration")
    parser.add_argument("-fv", "--fixed-volume", dest="fixed_volume", metavar="PATH", default="-", required=True,
                        help="Fixed volume to be used for registration")
    parser.add_argument("-mv", "--moving-volume", dest="moving_volume", metavar="PATH", default="-", required=True,
                        help="Moving volume to be used for registration")
    parser.add_argument("-it", "--initial-transform", dest="initial_transform", metavar="PATH", default="-",
                        required=False, help="Initial rigid transform for re-registration")
    parser.add_argument("-o", "--output-directory", dest="output_directory", metavar="PATH", default="-",
                        required=False, help="Output directory for registration result")

    args = parser.parse_args(argv)

    targets = None

    for inputFile in [args.fixed_label, args.moving_label, args.fixed_volume, args.moving_volume]:
      if not os.path.isfile(inputFile):
        raise AttributeError, "File not found: %s" % inputFile

    success, fixedLabel = slicer.util.loadLabelVolume(args.fixed_label, returnNode=True)
    success, movingLabel = slicer.util.loadLabelVolume(args.moving_label, returnNode=True)
    success, fixedVolume = slicer.util.loadVolume(args.fixed_volume, returnNode=True)
    success, movingVolume = slicer.util.loadVolume(args.moving_volume, returnNode=True)

    logic = SliceTrackerRegistrationLogic()
    logic.runRegistration(fixedVolume=fixedVolume, movingVolume=movingVolume, fixedLabel=fixedLabel,
                          movingLabel=movingLabel, targets=targets)

    if args.output_directory != "-":
      logic.registrationResult.save(args.output_directory)

  except Exception, e:
    print e
  sys.exit(0)

if __name__ == "__main__":
  main(sys.argv[1:])
