import sys, os
import qt, vtk
import csv, re, numpy
import logging
import slicer

import SimpleITK as sitk
import sitkUtils

from ..algorithms.zFrameRegistration import LineMarkerRegistration, OpenSourceZFrameRegistration
from ..constants import SliceTrackerConstants
from base import SliceTrackerStepLogic, SliceTrackerStep

from SlicerProstateUtils.decorators import logmethod
from SlicerProstateUtils.helpers import SliceAnnotation


class SliceTrackerZFrameRegistrationStepLogic(SliceTrackerStepLogic):

  ZFRAME_MODEL_PATH = 'zframe-model.vtk'
  ZFRAME_TEMPLATE_CONFIG_FILE_NAME = 'ProstateTemplate.csv'
  ZFRAME_MODEL_NAME = 'ZFrameModel'
  ZFRAME_TEMPLATE_NAME = 'NeedleGuideTemplate'
  ZFRAME_TEMPLATE_PATH_NAME = 'NeedleGuideNeedlePath'
  # COMPUTED_NEEDLE_MODEL_NAME = 'ComputedNeedleModel'

  @property
  def templateSuccessfulLoaded(self):
    return self.tempModelNode and self.pathModelNode

  @property
  def zFrameSuccessfulLoaded(self):
    return self.zFrameModelNode

  def __init__(self):
    super(SliceTrackerZFrameRegistrationStepLogic, self).__init__()
    self.cropVolumeLogic = slicer.modules.cropvolume.logic()
    self.setupSliceWidgets()
    self.resetAndInitializeData()

  def resetAndInitializeData(self):
    self.zFrameModelNode = None
    self.zFrameTransform = None

    self.showTemplatePath = False
    self.showNeedlePath = False

    self.needleModelNode = None
    self.tempModelNode = None
    self.pathModelNode = None
    self.templateConfig = []
    self.templateMaxDepth = []
    self.pathOrigins = []  ## Origins of needle paths (after transformation by parent transform node)
    self.pathVectors = []  ## Normal vectors of needle paths (after transformation by parent transform node)

    self.clearOldNodes()
    self.loadZFrameModel()
    self.loadTemplateConfigFile()

  def cleanup(self):
    pass

  def clearOldNodes(self):
    self.clearOldNodesByName(self.ZFRAME_TEMPLATE_NAME)
    self.clearOldNodesByName(self.ZFRAME_TEMPLATE_PATH_NAME)
    self.clearOldNodesByName(self.ZFRAME_MODEL_NAME)
    # self.clearOldNodesByName(self.COMPUTED_NEEDLE_MODEL_NAME)

  def loadZFrameModel(self):
    zFrameModelPath = os.path.join(self.resourcesPath, "zframe", self.ZFRAME_MODEL_PATH)
    if not self.zFrameModelNode:
      _, self.zFrameModelNode = slicer.util.loadModel(zFrameModelPath, returnNode=True)
      self.zFrameModelNode.SetName(self.ZFRAME_MODEL_NAME)
      slicer.mrmlScene.AddNode(self.zFrameModelNode)
      modelDisplayNode = self.zFrameModelNode.GetDisplayNode()
      modelDisplayNode.SetColor(1, 1, 0)
    self.zFrameModelNode.SetDisplayVisibility(False)

  def clearOldNodesByName(self, name):
    collection = slicer.mrmlScene.GetNodesByName(name)
    for index in range(collection.GetNumberOfItems()):
      slicer.mrmlScene.RemoveNode(collection.GetItemAsObject(index))

  def setupSliceWidgets(self):
    widget = slicer.app.layoutManager().sliceWidget("Red")
    self.redSliceView = widget.sliceView()
    self.redSliceLogic = widget.sliceLogic()

  def loadTemplateConfigFile(self):
    self.templateIndex = []
    self.templateConfig = []

    defaultTemplateFile = os.path.join(self.resourcesPath, "zframe", self.ZFRAME_TEMPLATE_CONFIG_FILE_NAME)

    reader = csv.reader(open(defaultTemplateFile, 'rb'))
    try:
      next(reader)
      for row in reader:
        self.templateIndex.append(row[0:2])
        self.templateConfig.append([float(row[2]), float(row[3]), float(row[4]),
                                    float(row[5]), float(row[6]), float(row[7]),
                                    float(row[8])])
    except csv.Error as e:
      print('file %s, line %d: %s' % (defaultTemplateFile, reader.line_num, e))
      return

    self.createTemplateAndNeedlePathModel()
    self.setTemplateVisibility(0)
    self.setTemplatePathVisibility(0)
    self.setNeedlePathVisibility(0)
    self.updateTemplateVectors()

  def createTemplateAndNeedlePathModel(self):
    self.templatePathVectors = []
    self.templatePathOrigins = []

    self.checkAndCreateTemplateModelNode()
    self.checkAndCreatePathModelNode()

    pathModelAppend = vtk.vtkAppendPolyData()
    templateModelAppend = vtk.vtkAppendPolyData()

    for row in self.templateConfig:
      p, n = self.extractPointsAndNormalVectors(row)

      tempTubeFilter = self.createTubeFilter(p[0], p[1], radius=1.0, numSides=18)
      templateModelAppend.AddInputData(tempTubeFilter.GetOutput())
      templateModelAppend.Update()

      pathTubeFilter = self.createTubeFilter(p[0], p[2], radius=0.8, numSides=18)
      pathModelAppend.AddInputData(pathTubeFilter.GetOutput())
      pathModelAppend.Update()

      self.templatePathOrigins.append([row[0], row[1], row[2], 1.0])
      self.templatePathVectors.append([n[0], n[1], n[2], 1.0])
      self.templateMaxDepth.append(row[6])

    self.tempModelNode.SetAndObservePolyData(templateModelAppend.GetOutput())
    modelDisplayNode = self.tempModelNode.GetDisplayNode()
    modelDisplayNode.SetColor(0.5,0,1)
    self.pathModelNode.SetAndObservePolyData(pathModelAppend.GetOutput())
    modelDisplayNode = self.pathModelNode.GetDisplayNode()
    modelDisplayNode.SetColor(0.8,0.5,1)

  def extractPointsAndNormalVectors(self, row):
    p1 = numpy.array(row[0:3])
    p2 = numpy.array(row[3:6])
    v = p2-p1
    nl = numpy.linalg.norm(v)
    n = v/nl  # normal vector
    l = row[6]
    p3 = p1 + l * n
    return [p1, p2, p3], n

  def createTubeFilter(self, start, end, radius, numSides):
    lineSource = vtk.vtkLineSource()
    lineSource.SetPoint1(start)
    lineSource.SetPoint2(end)
    tubeFilter = vtk.vtkTubeFilter()

    tubeFilter.SetInputConnection(lineSource.GetOutputPort())
    tubeFilter.SetRadius(radius)
    tubeFilter.SetNumberOfSides(numSides)
    tubeFilter.CappingOn()
    tubeFilter.Update()
    return tubeFilter

  def checkAndCreateTemplateModelNode(self):
    if self.tempModelNode is None:
      self.tempModelNode = self.createModelNode(self.ZFRAME_TEMPLATE_NAME)
      self.setAndObserveDisplayNode(self.tempModelNode)
      self.modelNodeTag = self.tempModelNode.AddObserver(slicer.vtkMRMLTransformableNode.TransformModifiedEvent,
                                                         self.updateTemplateVectors)

  def checkAndCreatePathModelNode(self):
    if self.pathModelNode is None:
      self.pathModelNode = self.createModelNode(self.ZFRAME_TEMPLATE_PATH_NAME)
      self.setAndObserveDisplayNode(self.pathModelNode)

  def updateTemplateVectors(self, observee=None, event=None):
    if self.tempModelNode is None:
      return

  def _setModelVisibility(self, node, visible):
    dnode = node.GetDisplayNode()
    if dnode is not None:
      dnode.SetVisibility(visible)

  def _setModelSliceIntersectionVisibility(self, node, visible):
    dnode = node.GetDisplayNode()
    if dnode is not None:
      dnode.SetSliceIntersectionVisibility(visible)

  def setZFrameVisibility(self, visibility):
    self._setModelVisibility(self.zFrameModelNode, visibility)
    self._setModelSliceIntersectionVisibility(self.zFrameModelNode, visibility)

  def setTemplateVisibility(self, visibility):
    self._setModelVisibility(self.tempModelNode, visibility)

  def setTemplatePathVisibility(self, visibility):
    self.showTemplatePath = visibility
    self._setModelVisibility(self.pathModelNode, visibility)
    self._setModelSliceIntersectionVisibility(self.pathModelNode, visibility)

  def setNeedlePathVisibility(self, visibility):
    self.showNeedlePath = visibility
    if self.needleModelNode:
      self._setModelVisibility(self.needleModelNode, visibility)
      self._setModelSliceIntersectionVisibility(self.needleModelNode, visibility)

  @logmethod(logging.INFO)
  def runZFrameRegistration(self, inputVolume, algorithm, **kwargs):
    registration = algorithm(inputVolume)
    if isinstance(registration, OpenSourceZFrameRegistration):
      registration.runRegistration(start=kwargs.pop("startSlice"), end=kwargs.pop("endSlice"))
    elif isinstance(registration, LineMarkerRegistration):
      registration.runRegistration()
    self.session.data.zFrameTransform = registration.getOutputTransformation()
    return True

  def getROIMinCenterMaxSliceNumbers(self, coverTemplateROI):
    center = [0.0, 0.0, 0.0]
    coverTemplateROI.GetXYZ(center)
    bounds = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    coverTemplateROI.GetRASBounds(bounds)
    pMin = [bounds[0], bounds[2], bounds[4]]
    pMax = [bounds[1], bounds[3], bounds[5]]
    return [self.getIJKForXYZ(pMin)[2], self.getIJKForXYZ(center)[2], self.getIJKForXYZ(pMax)[2]]

  def getIJKForXYZ(self, p):
    def roundInt(value):
      try:
        return int(round(value))
      except ValueError:
        return 0

    xyz = self.redSliceView.convertRASToXYZ(p)
    layerLogic = self.redSliceLogic.GetBackgroundLayer()
    xyToIJK = layerLogic.GetXYToIJKTransform()
    ijkFloat = xyToIJK.TransformDoublePoint(xyz)
    ijk = [roundInt(value) for value in ijkFloat]
    return ijk

  def getStartEndWithConnectedComponents(self, volume, center):
    address = sitkUtils.GetSlicerITKReadWriteAddress(volume.GetName())
    image = sitk.ReadImage(address)
    start = self.getStartSliceUsingConnectedComponents(center, image)
    end = self.getEndSliceUsingConnectedComponents(center, image)
    return start, end

  def getStartSliceUsingConnectedComponents(self, center, image):
    sliceIndex = start = center
    while sliceIndex > 0:
      if self.getIslandCount(image, sliceIndex) > 6:
        start = sliceIndex
        sliceIndex -= 1
        continue
      break
    return start

  def getEndSliceUsingConnectedComponents(self, center, image):
    imageSize = image.GetSize()
    sliceIndex = end = center
    while sliceIndex < imageSize[2]:
      if self.getIslandCount(image, sliceIndex) > 6:
        end = sliceIndex
        sliceIndex += 1
        continue
      break
    return end

  @staticmethod
  def getIslandCount(image, index):
    imageSize = image.GetSize()
    index = [0, 0, index]
    extractor = sitk.ExtractImageFilter()
    extractor.SetSize([imageSize[0], imageSize[1], 0])
    extractor.SetIndex(index)
    slice = extractor.Execute(image)
    cc = sitk.ConnectedComponentImageFilter()
    cc.Execute(slice)
    return cc.GetObjectCount()

  def createMaskedVolume(self, inputVolume, labelVolume):
    maskedVolume = slicer.vtkMRMLScalarVolumeNode()
    maskedVolume.SetName("maskedTemplateVolume")
    slicer.mrmlScene.AddNode(maskedVolume)
    params = {'InputVolume': inputVolume, 'MaskVolume': labelVolume, 'OutputVolume': maskedVolume}
    slicer.cli.run(slicer.modules.maskscalarvolume, None, params, wait_for_completion=True)
    return maskedVolume

  def createLabelMapFromCroppedVolume(self, volume):
    labelVolume = self.volumesLogic.CreateAndAddLabelVolume(volume, "labelmap")
    imagedata = labelVolume.GetImageData()
    imageThreshold = vtk.vtkImageThreshold()
    imageThreshold.SetInputData(imagedata)
    imageThreshold.ThresholdBetween(0, 2000)
    imageThreshold.SetInValue(1)
    imageThreshold.Update()
    labelVolume.SetAndObserveImageData(imageThreshold.GetOutput())
    return labelVolume

  def createCroppedVolume(self, inputVolume, roi):
    cropVolumeParameterNode = slicer.vtkMRMLCropVolumeParametersNode()
    cropVolumeParameterNode.SetROINodeID(roi.GetID())
    cropVolumeParameterNode.SetInputVolumeNodeID(inputVolume.GetID())
    cropVolumeParameterNode.SetVoxelBased(True)
    self.cropVolumeLogic.Apply(cropVolumeParameterNode)
    croppedVolume = slicer.mrmlScene.GetNodeByID(cropVolumeParameterNode.GetOutputVolumeNodeID())
    return croppedVolume


class SliceTrackerZFrameRegistrationStep(SliceTrackerStep):

  NAME = "ZFrame Registration"
  LogicClass = SliceTrackerZFrameRegistrationStepLogic

  def __init__(self):
    self.annotationLogic = slicer.modules.annotations.logic()
    self.zFrameRegistrationClass = getattr(sys.modules[__name__], self.getSetting("ZFrame_Registration_Class_Name"))

    self.roiObserverTag = None
    self.coverTemplateROI = None
    self.zFrameCroppedVolume = None
    self.zFrameLabelVolume = None
    self.zFrameMaskedVolume = None

    self.zFrameClickObserver = None
    self.zFrameInstructionAnnotation = None

    self.templateVolume = None

    super(SliceTrackerZFrameRegistrationStep, self).__init__()

  def setupIcons(self):
    self.zFrameIcon = self.createIcon('icon-zframe.png')
    self.needleIcon = self.createIcon('icon-needle.png')
    self.templateIcon = self.createIcon('icon-template.png')

  def setup(self):
    self.zFrameRegistrationGroupBox = qt.QGroupBox()
    self.zFrameRegistrationGroupBoxGroupBoxLayout = qt.QGridLayout()
    self.zFrameRegistrationGroupBox.setLayout(self.zFrameRegistrationGroupBoxGroupBoxLayout)

    self.applyZFrameRegistrationButton = self.createButton("Run ZFrame Registration", enabled=False)

    self.zFrameRegistrationManualIndexesGroupBox = qt.QGroupBox("Use manual start/end indexes")
    self.zFrameRegistrationManualIndexesGroupBox.setCheckable(True)
    self.zFrameRegistrationManualIndexesGroupBoxLayout = qt.QGridLayout()
    self.zFrameRegistrationManualIndexesGroupBox.setLayout(self.zFrameRegistrationManualIndexesGroupBoxLayout)

    self.zFrameRegistrationStartIndex = qt.QSpinBox()
    self.zFrameRegistrationEndIndex = qt.QSpinBox()

    hBox = self.createHLayout([qt.QLabel("start"), self.zFrameRegistrationStartIndex,
                               qt.QLabel("end"),self.zFrameRegistrationEndIndex])
    self.zFrameRegistrationManualIndexesGroupBoxLayout.addWidget(hBox, 1, 1, qt.Qt.AlignRight)

    self.approveZFrameRegistrationButton = self.createButton("Confirm registration accuracy",
                                                             enabled=self.zFrameRegistrationClass is LineMarkerRegistration)
    self.retryZFrameRegistrationButton = self.createButton("Reset", enabled=False,
                                                           visible=self.zFrameRegistrationClass is OpenSourceZFrameRegistration)

    buttons = self.createVLayout([self.applyZFrameRegistrationButton, self.approveZFrameRegistrationButton,
                                  self.retryZFrameRegistrationButton])
    self.zFrameRegistrationGroupBoxGroupBoxLayout.addWidget(self.createHLayout([buttons,
                                                                                self.zFrameRegistrationManualIndexesGroupBox]))

    self.zFrameRegistrationGroupBoxGroupBoxLayout.setRowStretch(1, 1)
    self.layout().addWidget(self.zFrameRegistrationGroupBox)

  def setupAdditionalViewSettingButtons(self):
    iconSize = qt.QSize(24, 24)
    self.showZFrameModelButton = self.createButton("", icon=self.zFrameIcon, iconSize=iconSize, checkable=True, toolTip="Display zFrame model")
    self.showTemplateButton = self.createButton("", icon=self.templateIcon, iconSize=iconSize, checkable=True, toolTip="Display template")
    # self.showNeedlePathButton = self.createButton("", icon=self.needleIcon, iconSize=iconSize, checkable=True, toolTip="Display needle path")
    self.showTemplatePathButton = self.createButton("", icon=self.templateIcon, iconSize=iconSize, checkable=True, toolTip="Display template paths")
    self.viewSettingButtons = [self.showZFrameModelButton, self.showTemplateButton]

  def setupConnections(self):
    self.retryZFrameRegistrationButton.clicked.connect(self.onRetryZFrameRegistrationButtonClicked)
    self.approveZFrameRegistrationButton.clicked.connect(self.onApproveZFrameRegistrationButtonClicked)
    self.applyZFrameRegistrationButton.clicked.connect(self.onApplyZFrameRegistrationButtonClicked)

    self.showZFrameModelButton.connect('toggled(bool)', self.onShowZFrameModelToggled)
    self.showTemplateButton.connect('toggled(bool)', self.onShowZFrameTemplateToggled)
    self.showTemplatePathButton.connect('toggled(bool)', self.onShowTemplatePathToggled)
    # self.showNeedlePathButton.connect('toggled(bool)', self.onShowNeedlePathToggled)

  def setupSessionObservers(self):
    super(SliceTrackerZFrameRegistrationStep, self).setupSessionObservers()
    self.session.addEventObserver(self.session.InitiateZFrameCalibrationEvent, self.onInitiateZFrameCalibration)

  def removeSessionEventObservers(self):
    super(SliceTrackerZFrameRegistrationStep, self).removeSessionEventObservers()
    self.session.removeEventObserver(self.session.InitiateZFrameCalibrationEvent, self.onInitiateZFrameCalibration)

  def onShowZFrameModelToggled(self, checked):
    self.logic.setZFrameVisibility(checked)

  def onShowZFrameTemplateToggled(self, checked):
    self.logic.setTemplateVisibility(checked)

  def onShowTemplatePathToggled(self, checked):
    self.logic.setTemplatePathVisibility(checked)

  def onShowNeedlePathToggled(self, checked):
    self.logic.setNeedlePathVisibility(checked)

  def resetViewSettingButtons(self):
    self.showTemplateButton.enabled = self.logic.templateSuccessfulLoaded
    self.showTemplatePathButton.enabled = self.logic.templateSuccessfulLoaded
    self.showZFrameModelButton.enabled = self.logic.zFrameSuccessfulLoaded

  def save(self, directory):
    # TODO
    pass

  def onLayoutChanged(self):
    pass

  def onInitiateZFrameCalibration(self, caller, event):
    self.active = True

    templateVolume = self.session.currentSeriesVolume
    if self.templateVolume and templateVolume is not self.templateVolume:
      if not slicer.util.confirmYesNoDisplay("It looks like another %s was received. Do you want to use this one for"
                                             "calibration?" % self.getSetting("COVER_TEMPLATE")):
        return
    self.templateVolume = templateVolume
    self.initiateZFrameRegistrationStep()

  @vtk.calldata_type(vtk.VTK_STRING)
  def onCurrentSeriesChanged(self, caller, event, callData=None):
    if callData:
      self.showTemplatePathButton.checked = self.session.isTrackingPossible(callData) and \
                                            self.getSetting("COVER_PROSTATE", moduleName=self.MODULE_NAME) in callData

  def onLoadingMetadataSuccessful(self, caller, event):
    if self.session.zFrameRegistrationSuccessful:
      self.applyZFrameTransform()

  def onActivation(self):
    self.layoutManager.setLayout(SliceTrackerConstants.LAYOUT_FOUR_UP)
    self.showZFrameModelButton.checked = True
    self.showTemplateButton.checked = True
    self.showTemplatePathButton.checked = True
    if self.templateVolume:
      self.initiateZFrameRegistrationStep()

  def onDeactivation(self):
    self.showZFrameModelButton.checked = False
    self.showTemplateButton.checked = False
    self.showTemplatePathButton.checked = False
    self.zFrameRegistrationManualIndexesGroupBox.checked = False
    self.templateVolume = None

  def initiateZFrameRegistrationStep(self):
    self.resetZFrameRegistration()
    self.setupFourUpView(self.templateVolume)
    self.redSliceNode.SetSliceVisible(True)
    if self.zFrameRegistrationClass is OpenSourceZFrameRegistration:
      self.addROIObserver()
      self.activateCreateROIMode()
      self.addZFrameInstructions()

  def resetZFrameRegistration(self):
    self.applyZFrameRegistrationButton.enabled = False
    self.approveZFrameRegistrationButton.enabled = False
    self.retryZFrameRegistrationButton.enabled = False

    self.removeNodeFromMRMLScene(self.coverTemplateROI)
    self.removeNodeFromMRMLScene(self.zFrameCroppedVolume)
    self.removeNodeFromMRMLScene(self.zFrameLabelVolume)
    self.removeNodeFromMRMLScene(self.zFrameMaskedVolume)
    self.removeNodeFromMRMLScene(self.session.data.zFrameTransform)

  def addROIObserver(self):
    @vtk.calldata_type(vtk.VTK_OBJECT)
    def onNodeAdded(caller, event, calldata):
      node = calldata
      if isinstance(node, slicer.vtkMRMLAnnotationROINode):
        self.removeROIObserver()
        self.coverTemplateROI = node
        self.applyZFrameRegistrationButton.enabled = self.isRegistrationPossible()

    if self.roiObserverTag:
      self.removeROIObserver()
    self.roiObserverTag = slicer.mrmlScene.AddObserver(slicer.vtkMRMLScene.NodeAddedEvent, onNodeAdded)

  def isRegistrationPossible(self):
    return self.coverTemplateROI is not None

  def removeROIObserver(self):
    if self.roiObserverTag:
      self.roiObserverTag = slicer.mrmlScene.RemoveObserver(self.roiObserverTag)

  def activateCreateROIMode(self):
    mrmlScene = self.annotationLogic.GetMRMLScene()
    selectionNode = mrmlScene.GetNthNodeByClass(0, "vtkMRMLSelectionNode")
    selectionNode.SetReferenceActivePlaceNodeClassName("vtkMRMLAnnotationROINode")
    self.annotationLogic.StartPlaceMode(False)

  def addZFrameInstructions(self, step=1):
    self.zFrameStep = step
    text = SliceTrackerConstants.ZFrame_INSTRUCTION_STEPS[self.zFrameStep]
    self.zFrameInstructionAnnotation = SliceAnnotation(self.redWidget, text, yPos=55, horizontalAlign="center",
                                                       opacity=0.6, color=(0,0.6,0))
    self.zFrameClickObserver = self.redSliceViewInteractor.AddObserver(vtk.vtkCommand.LeftButtonReleaseEvent,
                                                      self.onZFrameStepAccomplished)
    # TODO
    # self.onShowAnnotationsToggled(self.showAnnotationsButton.checked)

  def onZFrameStepAccomplished(self, observee, event):
    self.removeZFrameInstructionAnnotation()
    nextStep = self.zFrameStep + 1
    if nextStep in SliceTrackerConstants.ZFrame_INSTRUCTION_STEPS.keys():
      self.addZFrameInstructions(nextStep)

  def removeZFrameInstructionAnnotation(self):
    if hasattr(self, "zFrameInstructionAnnotation") and self.zFrameInstructionAnnotation:
      self.zFrameInstructionAnnotation.remove()
      self.zFrameInstructionAnnotation = None
    if self.zFrameClickObserver :
      self.redSliceViewInteractor.RemoveObserver(self.zFrameClickObserver)
      self.zFrameClickObserver = None

  def onApplyZFrameRegistrationButtonClicked(self):
    # progress = self.createProgressDialog(maximum=2, value=1)
    # progress.labelText = '\nZFrame registration'
    zFrameTemplateVolume = self.templateVolume
    try:
      if self.zFrameRegistrationClass is OpenSourceZFrameRegistration:
        self.annotationLogic.SetAnnotationLockedUnlocked(self.coverTemplateROI.GetID())
        self.zFrameCroppedVolume = self.logic.createCroppedVolume(zFrameTemplateVolume, self.coverTemplateROI)
        self.zFrameLabelVolume = self.logic.createLabelMapFromCroppedVolume(self.zFrameCroppedVolume)
        self.zFrameMaskedVolume = self.logic.createMaskedVolume(zFrameTemplateVolume, self.zFrameLabelVolume)
        self.zFrameMaskedVolume.SetName(zFrameTemplateVolume.GetName() + "-label")

        if not self.zFrameRegistrationManualIndexesGroupBox.checked:
          start, center, end = self.logic.getROIMinCenterMaxSliceNumbers(self.coverTemplateROI)
          otsuOutputVolume = self.logic.applyOtsuFilter(self.zFrameMaskedVolume)
          self.logic.dilateMask(otsuOutputVolume)
          start, end = self.logic.getStartEndWithConnectedComponents(otsuOutputVolume, center)
          self.zFrameRegistrationStartIndex.value = start
          self.zFrameRegistrationEndIndex.value = end
        else:
          start = self.zFrameRegistrationStartIndex.value
          end = self.zFrameRegistrationEndIndex.value
        self.logic.runZFrameRegistration(self.zFrameMaskedVolume, self.zFrameRegistrationClass,
                                         startSlice=start, endSlice=end)
      else:
        self.logic.runZFrameRegistration(zFrameTemplateVolume, self.zFrameRegistrationClass)

      self.applyZFrameTransform()

    except AttributeError as exc:
      # progress.close()
      slicer.util.errorDisplay("An error occurred. For further information click 'Show Details...'",
                   windowTitle=self.__class__.__name__, detailedText=str(exc.message))
    else:
      self.setBackgroundToVolumeID(zFrameTemplateVolume.GetID())
      self.approveZFrameRegistrationButton.enabled = True
      self.retryZFrameRegistrationButton.enabled = True
      # progress.setValue(2)
      # progress.close()

  def applyZFrameTransform(self):
    for node in [node for node in
                 [self.logic.pathModelNode, self.logic.tempModelNode,
                  self.logic.zFrameModelNode, self.logic.needleModelNode] if node]:
      node.SetAndObserveTransformNodeID(self.session.data.zFrameTransform.GetID())

  def onApproveZFrameRegistrationButtonClicked(self):
    self.redSliceNode.SetSliceVisible(False)
    if self.zFrameRegistrationClass is OpenSourceZFrameRegistration:
      self.annotationLogic.SetAnnotationVisibility(self.coverTemplateROI.GetID())
    self.session.zFrameRegistrationSuccessful = True

  def onRetryZFrameRegistrationButtonClicked(self):
    self.removeZFrameInstructionAnnotation()
    self.annotationLogic.SetAnnotationVisibility(self.coverTemplateROI.GetID())
    self.initiateZFrameRegistrationStep()