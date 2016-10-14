import slicer, qt, vtk
import os, logging
from slicer.ScriptedLoadableModule import *

from SlicerProstateUtils.mixins import ModuleWidgetMixin, ModuleLogicMixin

from EditorLib import ColorBox


class VolumeClipToLabel(ScriptedLoadableModule):

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Volume clip to label"
    self.parent.categories = ["Segmentation"]
    self.parent.dependencies = ["SlicerProstate"]
    self.parent.contributors = ["Christian Herz (SPL), Peter Behringer (SPL)"]
    self.parent.helpText = """ VolumeClipLabel uses the VolumeClip for creating a label map"""
    self.parent.acknowledgementText = """Surgical Planning Laboratory, Brigham and Women's Hospital, Harvard
                                          Medical School, Boston, USA This work was supported in part by the National
                                          Institutes of Health through grants U24 CA180918,
                                          R01 CA111288 and P41 EB015898."""


class VolumeClipToLabelWidget(ModuleWidgetMixin, ScriptedLoadableModuleWidget):

  SegmentationFinishedEvent = vtk.vtkCommand.UserEvent + 101
  SegmentationStartedEvent = vtk.vtkCommand.UserEvent + 102
  SegmentationCanceledEvent = vtk.vtkCommand.UserEvent + 103

  @property
  def imageVolume(self):
      return self.imageVolumeSelector.currentNode()

  def __init__(self, parent=None):
    ScriptedLoadableModuleWidget.__init__(self, parent)
    self.modulePath = os.path.dirname(slicer.util.modulePath(self.moduleName))
    self.logic = VolumeClipToLabelLogic()

  def isActive(self):
    return self.markupNodeObserver is not None

  def onReload(self):
    if self.isActive():
      self.deactivateQuickSegmentationMode(canceled=True)
    ScriptedLoadableModuleWidget.onReload(self)

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)
    try:
      import VolumeClipWithModel
    except ImportError:
      return slicer.util.warningDisplay("Error: Could not find extension VolumeClip. Open Slicer Extension Manager and install "
                                        "VolumeClip.", "Missing Extension")
    self.initializeMembers()
    self.setupIcons()
    self.setupSelectorArea()
    self.setupColorFrame()
    self.setupButtons()
    self.setupConnections()

    self.layout.addStretch(1)

  def initializeMembers(self):
    self.markupNodeObserver = None
    self.undoRedoEventObserver = None
    self.colorBox = None

  def setupButtons(self):

    iconSize = qt.QSize(24, 24)
    self.quickSegmentationButton = self.createButton('Quick Mode', icon=self.quickSegmentationIcon, iconSize=iconSize,
                                                     checkable=True, objectName="quickSegmentationButton", enabled=False)
    self.applySegmentationButton = self.createButton("", icon=self.greenCheckIcon, iconSize=iconSize,
                                                     enabled=False, objectName="applyButton")
    self.cancelSegmentationButton = self.createButton("", icon=self.cancelSegmentationIcon,
                                                      iconSize=iconSize, enabled=False, objectName="cancelButton")
    self.undoButton = self.createButton("", icon=self.undoIcon, iconSize=iconSize, enabled=False, objectName="undoButton")
    self.redoButton = self.createButton("", icon=self.redoIcon, iconSize=iconSize, enabled=False, objectName="redoButton")

    self.segmentationButtons = self.createHLayout([self.quickSegmentationButton, self.applySegmentationButton,
                                              self.cancelSegmentationButton, self.undoButton, self.redoButton])
    self.layout.addWidget(self.segmentationButtons)

  def setupColorFrame(self):
    self.colorGroupBox = qt.QGroupBox("Color")
    self.colorGroupBoxLayout = qt.QHBoxLayout()
    self.colorGroupBox.setLayout(self.colorGroupBoxLayout)

    self.colorSpin = qt.QSpinBox()
    self.colorSpin.objectName = 'ColorSpinBox'
    self.colorSpin.setMaximum(64000) # TODO: should be detected from colorNode maximum value
    self.colorSpin.setValue(1)
    self.colorSpin.setToolTip( "Click colored patch at right to bring up color selection pop up window." )
    self.colorGroupBoxLayout.addWidget(self.colorSpin)

    self.colorPatch = self.createButton("", objectName="ColorPatchButton")
    self.colorGroupBoxLayout.addWidget(self.colorPatch)
    self.layout.addWidget(self.colorGroupBox)

  def setupSelectorArea(self):
    self.imageVolumeLabel = self.createLabel("Image volume: ", objectName="imageVolumeLabel")
    self.imageVolumeSelector = self.createComboBox(nodeTypes=["vtkMRMLScalarVolumeNode", ""], showChildNodeTypes=False,
                                                   selectNodeUponCreation=True, toolTip="Pick algorithm input.",
                                                   objectName="imageVolumeSelector")
    self.labelMapLabel = self.createLabel("Output label: ", objectName="labelMapLabel")
    self.labelMapSelector = self.createComboBox(nodeTypes=["vtkMRMLLabelMapVolumeNode", ""], showChildNodeTypes=False,
                                                selectNodeUponCreation=True, toolTip="Output label node",
                                                addEnabled=True, removeEnabled=True, noneEnabled=True,
                                                objectName="outputLabelMapSelector")
    self.selectorsGroupBox = qt.QGroupBox()
    self.selectorsGroupBox.objectName = "selectorsGroupBox"
    self.selectorsGroupBoxLayout = qt.QGridLayout()
    self.selectorsGroupBox.setLayout(self.selectorsGroupBoxLayout)
    self.selectorsGroupBoxLayout.addWidget(self.imageVolumeLabel, 0, 0)
    self.selectorsGroupBoxLayout.addWidget(self.imageVolumeSelector, 0, 1)
    self.selectorsGroupBoxLayout.addWidget(self.labelMapLabel, 1, 0)
    self.selectorsGroupBoxLayout.addWidget(self.labelMapSelector, 1, 1)
    self.layout.addWidget(self.selectorsGroupBox)

  def setupIcons(self):
    self.greenCheckIcon = self.createIcon('icon-greenCheck.png')
    self.quickSegmentationIcon = self.createIcon('icon-quickSegmentation.png')
    self.cancelSegmentationIcon = self.createIcon('icon-cancelSegmentation.png')
    self.undoIcon = self.createIcon('icon-undo.png')
    self.redoIcon = self.createIcon('icon-redo.png')

  def setupConnections(self):
    self.imageVolumeSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.onImageVolumeSelected)
    self.quickSegmentationButton.connect('toggled(bool)', self.onQuickSegmentationButtonToggled)

    self.colorSpin.valueChanged.connect(self.onColorSpinChanged)
    self.colorPatch.clicked.connect(self.showColorBox)

    self.applySegmentationButton.clicked.connect(self.onQuickSegmentationFinished)
    self.cancelSegmentationButton.clicked.connect(self.onCancelSegmentationButtonClicked)
    self.redoButton.clicked.connect(self.logic.redo)
    self.undoButton.clicked.connect(self.logic.undo)

  def onColorSpinChanged(self, value):
    self.logic.outputLabelValue = value
    self.onColorSelected(value)

  def showColorBox(self):
    self.colorBox = ColorBox(parameterNode=self.parameterNode, parameter='label', colorNode=self.logic.colorNode,
                             selectCommand=self.onColorSelected)

  def onColorSelected(self, labelValue):
    colorNode = self.logic.colorNode
    if colorNode:
      self.logic.outputLabelValue = labelValue
      lut = colorNode.GetLookupTable()
      rgb = lut.GetTableValue(labelValue)
      self.colorPatch.setStyleSheet("background-color: rgb(%s,%s,%s)" % (rgb[0] * 255, rgb[1] * 255, rgb[2] * 255))
      self.colorSpin.setMaximum(colorNode.GetNumberOfColors() - 1)
      self.colorSpin.setValue(labelValue)

  def onImageVolumeSelected(self, node):
    self.setBackgroundVolumeForAllVisibleSliceViews(node)
    self.quickSegmentationButton.setEnabled(node!=None)
    self.colorPatch.setEnabled(node!=None)

  def setBackgroundToVolumeID(self, widget, volumeNode):
    compositeNode = widget.mrmlSliceCompositeNode()
    compositeNode.SetLabelVolumeID(None)
    compositeNode.SetForegroundVolumeID(None)
    compositeNode.SetBackgroundVolumeID(volumeNode.GetID() if volumeNode else None)

  def setBackgroundVolumeForAllVisibleSliceViews(self, volume):
    for widget in [w for w in self.getAllVisibleWidgets() if w.sliceView().visible]:
      self.setBackgroundToVolumeID(widget, volume)

  def onQuickSegmentationButtonToggled(self, enabled):
    self.updateSegmentationButtons()
    self.imageVolumeSelector.enabled = not enabled
    if enabled:
      self.setBackgroundVolumeForAllVisibleSliceViews(self.imageVolume)
      self.activateQuickSegmentationMode()
    self.deactivateUndoRedoButtons()

  def deactivateUndoRedoButtons(self):
    self.redoButton.setEnabled(False)
    self.undoButton.setEnabled(False)

  def onQuickSegmentationFinished(self):
    if not self.logic.isSegmentationValid():
      if self.promptOnInvalidSegmentationDetected():
        self.invokeEvent(self.SegmentationCanceledEvent)
        return
      self.deactivateQuickSegmentationMode(canceled=True)
      self.quickSegmentationButton.checked = False
    else:
      self.processValidQuickSegmentationResult()

  def promptOnInvalidSegmentationDetected(self):
    return slicer.util.confirmYesNoDisplay("You need to set at least three points with an additional one situated on a "
                                           "distinct slice as the algorithm input in order to be able to create a "
                                           "proper segmentation. This step is essential for an efficient registration. "
                                           "Do you want to continue using the quick mode?", windowTitle="SliceTracker")

  def updateSegmentationButtons(self):
    self.quickSegmentationButton.setEnabled(not self.quickSegmentationButton.checked)
    self.applySegmentationButton.setEnabled(self.quickSegmentationButton.checked)
    self.cancelSegmentationButton.setEnabled(self.quickSegmentationButton.checked)

  def activateQuickSegmentationMode(self):
    self.logic.runQuickSegmentationMode()
    self.undoRedoEventObserver = self.logic.addEventObserver(self.logic.UndoRedoEvent, self.updateUndoRedoButtons)
    self.markupNodeObserver = self.logic.addEventObserver(vtk.vtkCommand.ModifiedEvent, self.updateUndoRedoButtons)
    self.invokeEvent(self.SegmentationStartedEvent)

  def deactivateQuickSegmentationMode(self, canceled=False):
    self.quickSegmentationButton.checked = False
    self.resetToRegularViewMode()
    self.undoRedoEventObserver = self.logic.removeEventObserver(self.logic.UndoRedoEvent, self.undoRedoEventObserver)
    self.markupNodeObserver = self.logic.removeEventObserver(vtk.vtkCommand.ModifiedEvent, self.markupNodeObserver)
    self.logic.stopQuickSegmentationMode(canceled)

  def updateUndoRedoButtons(self, observer=None, caller=None):
    self.redoButton.setEnabled(self.logic.redoPossible)
    self.undoButton.setEnabled(self.logic.undoPossible)

  def onCancelSegmentationButtonClicked(self):
    if slicer.util.confirmYesNoDisplay("Do you really want to cancel the segmentation process?",
                                       windowTitle="SliceTracker"):
      self.deactivateQuickSegmentationMode(canceled=True)
      self.invokeEvent(self.SegmentationCanceledEvent)

  def processValidQuickSegmentationResult(self):
    self.deactivateQuickSegmentationMode()
    node = self.imageVolumeSelector.currentNode()
    outputLabel = self.logic.labelMapFromClippingModel(node)
    outputLabel.SetName(node.GetName() + '-label')
    self.labelMapSelector.setCurrentNode(outputLabel)
    self.logic.markupsLogic.SetAllMarkupsVisibility(self.logic.inputMarkupNode, False)
    self.logic.clippingModelNode.SetDisplayVisibility(False)
    self.invokeEvent(self.SegmentationFinishedEvent, outputLabel)


class VolumeClipToLabelLogic(ModuleLogicMixin, ScriptedLoadableModuleLogic):

  UndoRedoEvent = vtk.vtkCommand.UserEvent + 102

  @property
  def undoPossible(self):
      return self.inputMarkupNode.GetNumberOfFiducials() > 0

  @property
  def redoPossible(self):
    return len(self.deletedMarkupPositions) > 0

  @property
  def colorNode(self):
    if not self._colorNode:
      self._colorNode = slicer.util.getNode('GenericAnatomyColors')
    return self._colorNode

  @colorNode.setter
  def colorNode(self, value):
    self._colorNode = value

  @property
  def outputLabelValue(self):
    return self._labelValue

  @outputLabelValue.setter
  def outputLabelValue(self, value):
    if self.clippingModelDisplayNode and self._colorNode:
      self.clippingModelDisplayNode.SetColor(self.labelValueToRGB(value))
    self._labelValue = value

  def __init__(self, outputLabelValue=None):
    ScriptedLoadableModuleLogic.__init__(self)
    self.markupsLogic = slicer.modules.markups.logic()
    self.clippingModelNode = None
    self.clippingModelDisplayNode = None
    self.inputMarkupNode = None
    self.deletedMarkups = None
    self.colorNode = None
    self.outputLabelValue = outputLabelValue
    self.deletedMarkupPositions = []

  def reset(self):
    if self.clippingModelNode:
      slicer.mrmlScene.RemoveNode(self.clippingModelNode)
    if self.inputMarkupNode:
      slicer.mrmlScene.RemoveNode(self.inputMarkupNode)
    self.resetQuickModeHistory()

  def resetQuickModeHistory(self, caller=None, event=None):
    self.deletedMarkupPositions = []

  def addInputMarkupNodeObserver(self):
    self.inputMarkupNodeObserver = self.inputMarkupNode.AddObserver(vtk.vtkCommand.ModifiedEvent,
                                                                    self.onMarkupModified)

  def removeInputMarkupNodeObserver(self):
    self.inputMarkupNodeObserver = self.inputMarkupNode.RemoveObserver(self.inputMarkupNodeObserver)

  def setupDisplayNode(self, displayNode=None, starBurst=False):
    if not displayNode:
      displayNode = slicer.vtkMRMLMarkupsDisplayNode()
      slicer.mrmlScene.AddNode(displayNode)
    displayNode.SetTextScale(0)
    displayNode.SetGlyphScale(2.5)
    if starBurst:
      displayNode.SetGlyphType(slicer.vtkMRMLAnnotationPointDisplayNode.StarBurst2D)
    return displayNode

  def runQuickSegmentationMode(self):
    self.reset()
    self.markupsLogic.StartPlaceMode(1)
    self.placeFiducials()
    self.addInputMarkupNodeObserver()

  def stopQuickSegmentationMode(self, canceled=False):
    self.removeInputMarkupNodeObserver()
    if canceled:
      self.reset()

  def updateModel(self, observer, caller):
    import VolumeClipWithModel
    clipLogic = VolumeClipWithModel.VolumeClipWithModelLogic()
    clipLogic.updateModelFromMarkup(self.inputMarkupNode, self.clippingModelNode)

  def onMarkupModified(self, caller, event):
    self.invokeEvent(vtk.vtkCommand.ModifiedEvent)
    self.resetQuickModeHistory()

  def isSegmentationValid(self):
    return self.inputMarkupNode.GetNumberOfFiducials() > 3 and self.validPointsForQuickModeSet()

  def validPointsForQuickModeSet(self):
    positions = self.getMarkupSlicePositions()
    return min(positions) != max(positions)

  def getMarkupSlicePositions(self):
    nOfControlPoints = self.inputMarkupNode.GetNumberOfFiducials()
    return [self.getTargetPosition(self.inputMarkupNode, index)[2] for index in range(nOfControlPoints)]

  def placeFiducials(self):
    self.clippingModelNode = slicer.vtkMRMLModelNode()
    self.clippingModelNode.SetName('clipModelNode')
    slicer.mrmlScene.AddNode(self.clippingModelNode)
    self.createAndConfigureClippingModelDisplayNode()
    self.createMarkupsFiducialNode()
    self.inputMarkupNode.AddObserver(vtk.vtkCommand.ModifiedEvent, self.updateModel)
    volumeClipPointsDisplayNode = self.setupDisplayNode()
    self.inputMarkupNode.SetAndObserveDisplayNodeID(volumeClipPointsDisplayNode.GetID())

  def createAndConfigureClippingModelDisplayNode(self):
    self.clippingModelDisplayNode = slicer.vtkMRMLModelDisplayNode()
    self.clippingModelDisplayNode.SetSliceIntersectionThickness(3)
    self.clippingModelDisplayNode.SetColor(self.labelValueToRGB(self.outputLabelValue) if self.outputLabelValue
                                           else [0.200, 0.800, 0.000])
    self.clippingModelDisplayNode.BackfaceCullingOff()
    self.clippingModelDisplayNode.SliceIntersectionVisibilityOn()
    self.clippingModelDisplayNode.SetOpacity(0.3)
    slicer.mrmlScene.AddNode(self.clippingModelDisplayNode)
    self.clippingModelNode.SetAndObserveDisplayNodeID(self.clippingModelDisplayNode.GetID())

  def createMarkupsFiducialNode(self):
    self.inputMarkupNode = slicer.vtkMRMLMarkupsFiducialNode()
    self.inputMarkupNode.SetName('inputMarkupNode')
    slicer.mrmlScene.AddNode(self.inputMarkupNode)

  def labelMapFromClippingModel(self, inputVolume, outputLabelValue=1, outputLabelMap=None):
    if not outputLabelMap:
      outputLabelMap = slicer.vtkMRMLLabelMapVolumeNode()
      slicer.mrmlScene.AddNode(outputLabelMap)

    if self.outputLabelValue:
      outputLabelValue = self.outputLabelValue

    params = {'sampleDistance': 0.1, 'labelValue': outputLabelValue, 'InputVolume': inputVolume.GetID(),
              'surface': self.clippingModelNode.GetID(), 'OutputVolume': outputLabelMap.GetID()}

    logging.debug(params)
    slicer.cli.run(slicer.modules.modeltolabelmap, None, params, wait_for_completion=True)

    if self.colorNode:
      displayNode = outputLabelMap.GetDisplayNode()
      displayNode.SetAndObserveColorNodeID(self.colorNode.GetID())
    return outputLabelMap

  def undo(self):
    numberOfTargets = self.inputMarkupNode.GetNumberOfFiducials()
    if not numberOfTargets:
      return
    pos = self.getTargetPosition(self.inputMarkupNode, numberOfTargets-1)
    self.deletedMarkupPositions.append(pos)
    self.removeInputMarkupNodeObserver()
    self.inputMarkupNode.RemoveMarkup(numberOfTargets - 1)
    self.addInputMarkupNodeObserver()
    self.invokeEvent(self.UndoRedoEvent)

  def redo(self):
    if not len(self.deletedMarkupPositions):
      return
    pos = self.deletedMarkupPositions.pop()
    self.removeInputMarkupNodeObserver()
    self.inputMarkupNode.AddFiducialFromArray(pos)
    self.addInputMarkupNodeObserver()
    self.invokeEvent(self.UndoRedoEvent)

  def labelValueToRGB(self, labelValue, colorNode=None):
    colorNode = colorNode if colorNode else self.colorNode
    if self.colorNode:
      lut = self.colorNode.GetLookupTable()
      rgb = lut.GetTableValue(labelValue)
      return [rgb[0], rgb[1], rgb[2]]
    return None