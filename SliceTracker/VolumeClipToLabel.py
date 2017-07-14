import slicer, qt, vtk
import os, logging
from slicer.ScriptedLoadableModule import *

from SlicerDevelopmentToolboxUtils.mixins import ModuleWidgetMixin, ModuleLogicMixin
from SlicerDevelopmentToolboxUtils.decorators import onModuleSelected
from SlicerDevelopmentToolboxUtils.icons import Icons

import EditorLib
from EditorLib import ColorBox
from Editor import EditorWidget


class VolumeClipToLabel(ScriptedLoadableModule):

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Volume clip to label"
    self.parent.categories = ["Segmentation"]
    self.parent.dependencies = ["SlicerDevelopmentToolbox"]
    self.parent.contributors = ["Christian Herz (SPL), Peter Behringer (SPL)"]
    self.parent.helpText = """ VolumeClipLabel uses the VolumeClip for creating a label map"""
    self.parent.acknowledgementText = """Surgical Planning Laboratory, Brigham and Women's Hospital, Harvard
                                          Medical School, Boston, USA This work was supported in part by the National
                                          Institutes of Health through grants U24 CA180918,
                                          R01 CA111288 and P41 EB015898."""


class VolumeClipToLabelWidget(ModuleWidgetMixin, ScriptedLoadableModuleWidget):

  SegmentationStartedEvent = vtk.vtkCommand.UserEvent + 101
  SegmentationCanceledEvent = vtk.vtkCommand.UserEvent + 102
  SegmentationFinishedEvent = vtk.vtkCommand.UserEvent + 103

  @property
  def imageVolume(self):
    return self.imageVolumeSelector.currentNode()

  @property
  def labelVolume(self):
    return self.labelMapSelector.currentNode()

  @property
  def selectorsGroupBoxVisible(self):
    return self.selectorsGroupBox.visible

  @selectorsGroupBoxVisible.setter
  def selectorsGroupBoxVisible(self, visible):
    self.selectorsGroupBox.visible = visible

  @property
  def colorGroupBoxVisible(self):
    return self.colorGroupBox.visible

  @colorGroupBoxVisible.setter
  def colorGroupBoxVisible(self, visible):
    self.colorGroupBox.visible = visible


  def __init__(self, parent=None, **kwargs):
    ScriptedLoadableModuleWidget.__init__(self, parent)
    self.modulePath = os.path.dirname(slicer.util.modulePath(self.moduleName))
    self.logic = VolumeClipToLabelLogic()
    self.markupNodeObserver = None
    self.colorBox = False
    self._processKwargs(**kwargs)

  def isActive(self):
    return self.markupNodeObserver is not None

  def onReload(self):
    if self.isActive():
      self.deactivateQuickSegmentationMode(cancelled=True)
    self.cleanup()
    ScriptedLoadableModuleWidget.onReload(self)

  def cleanup(self):
    self.layoutManager.layoutChanged.disconnect(self._onLayoutChanged)

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)
    try:
      import VolumeClipWithModel
    except ImportError:
      return slicer.util.warningDisplay("Error: Could not find extension VolumeClip. Open Slicer Extension Manager and "
                                        "install VolumeClip.", "Missing Extension")
    self._setupIcons()
    self._setupSelectorArea()
    self._setupColorFrame()
    self._setupButtons()
    self._setupConnections()
    self.colorSpin.setValue(1)
    self.layout.addStretch(1)

  def _setupIcons(self):
    self.quickSegmentationIcon = self.createIcon('icon-quickSegmentation.png')

  def _setupSelectorArea(self):
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

  def _setupColorFrame(self):
    self.colorGroupBox = qt.QGroupBox("Color")
    self.colorGroupBoxLayout = qt.QHBoxLayout()
    self.colorGroupBox.setLayout(self.colorGroupBoxLayout)

    self.colorSpin = qt.QSpinBox()
    self.colorSpin.objectName = 'ColorSpinBox'
    self.colorSpin.setMaximum(64000) # TODO: should be detected from colorNode maximum value
    self.colorSpin.setToolTip( "Click colored patch at right to bring up color selection pop up window." )
    self.colorGroupBoxLayout.addWidget(self.colorSpin)

    self.colorPatch = self.createButton("", objectName="ColorPatchButton")
    self.colorGroupBoxLayout.addWidget(self.colorPatch)
    self.layout.addWidget(self.colorGroupBox)

  def _setupButtons(self):
    iconSize = qt.QSize(36, 36)
    self.quickSegmentationButton = self.createButton('Quick Mode', icon=self.quickSegmentationIcon, iconSize=iconSize,
                                                     checkable=True, objectName="quickSegmentationButton", enabled=False,
                                                     toolTip="Start quick mode segmentation")
    self.applySegmentationButton = self.createButton("", icon=Icons.apply, iconSize=iconSize,
                                                     enabled=False, objectName="applyButton", toolTip="Apply")
    self.cancelSegmentationButton = self.createButton("", icon=Icons.cancel, iconSize=iconSize,
                                                      enabled=False, objectName="cancelButton", toolTip="Cancel")
    self.undoButton = self.createButton("", icon=Icons.undo, iconSize=iconSize, enabled=False, toolTip="Undo",
                                        objectName="undoButton")
    self.redoButton = self.createButton("", icon=Icons.redo, iconSize=iconSize, enabled=False, toolTip="Redo",
                                        objectName="redoButton")

    self.editorWidgetButton = self.createButton("", icon=Icons.settings, toolTip="Show Label Editor",
                                                checkable=True, enabled=False, iconSize=qt.QSize(36, 36))

    self._setupEditorWidget()
    self.segmentationButtons = self.createHLayout([self.quickSegmentationButton, self.applySegmentationButton,
                                                   self.cancelSegmentationButton, self.undoButton, self.redoButton,
                                                   self.editorWidgetButton])
    self.layout.addWidget(self.segmentationButtons)
    self.layout.addWidget(self.editorWidgetParent, 1, 0)

  def _setupEditorWidget(self):
    self.editorWidgetParent = slicer.qMRMLWidget()
    self.editorWidgetParent.setLayout(qt.QVBoxLayout())
    self.editorWidgetParent.setMRMLScene(slicer.mrmlScene)
    self.editorWidgetParent.hide()
    self.editUtil = EditorLib.EditUtil.EditUtil()
    self.editorWidget = EditorWidget(parent=self.editorWidgetParent, showVolumesFrame=False)
    self.editorWidget.setup()
    self.editorParameterNode = self.editUtil.getParameterNode()

  def _setupConnections(self):
    self.imageVolumeSelector.connect('currentNodeChanged(vtkMRMLNode*)', self._onImageVolumeSelected)
    self.labelMapSelector.connect('currentNodeChanged(vtkMRMLNode*)', self._onLabelMapSelected)
    self.quickSegmentationButton.connect('toggled(bool)', self.onQuickSegmentationButtonToggled)

    self.colorSpin.valueChanged.connect(self._onColorSpinChanged)
    self.colorPatch.clicked.connect(self._showColorBox)

    self.applySegmentationButton.clicked.connect(self.onQuickSegmentationFinished)
    self.cancelSegmentationButton.clicked.connect(self.onCancelSegmentationButtonClicked)
    self.redoButton.clicked.connect(self.logic.redo)
    self.undoButton.clicked.connect(self.logic.undo)
    self.editorWidgetButton.connect('toggled(bool)', self._onEditorGearIconChecked)

    self.layoutManager.layoutChanged.connect(self._onLayoutChanged)

  def _onEditorGearIconChecked(self, enabled):
    self.editorWidgetParent.visible = enabled
    if enabled:
      self.editorParameterNode.SetParameter('effect', 'DrawEffect')
      self.editUtil.setLabelOutline(1)
    else:
      self.editorParameterNode.SetParameter('effect', 'DefaultTool')

  @onModuleSelected("VolumeClipToLabel")
  def _onLayoutChanged(self, layout):
    self.setBackgroundToVolumeID(self.imageVolume)

  def _onColorSpinChanged(self, value):
    self.logic.outputLabelValue = value
    self.editUtil.setLabel(value)
    self._onColorSelected(value)

  def _showColorBox(self):
    if self.colorBox:
      self.colorBox.parent.close()
    self.colorBox = ColorBox(parameterNode=self.parameterNode, parameter='label', colorNode=self.logic.colorNode,
                             selectCommand=self._onColorSelected)

  def _onColorSelected(self, labelValue):
    self.colorBox = None
    self.logic.outputLabelValue = labelValue
    lut = self.logic.colorNode.GetLookupTable()
    rgb = lut.GetTableValue(labelValue)
    self.colorPatch.setStyleSheet("background-color: rgb(%s,%s,%s)" % (rgb[0] * 255, rgb[1] * 255, rgb[2] * 255))
    self.colorSpin.setMaximum(self.logic.colorNode.GetNumberOfColors() - 1)
    self.colorSpin.setValue(labelValue)

  def _onImageVolumeSelected(self, node):
    try:
      self.logic.seriesNumber = node.GetName().split(": ")[0]
    except (AttributeError, KeyError):
      self.logic.seriesNumber = None

    self.setBackgroundToVolumeID(node)
    self.quickSegmentationButton.setEnabled(node!=None)
    self.colorPatch.setEnabled(node!=None)
    self._updateGearButtonAvailability()

  def _onLabelMapSelected(self, node):
    self._updateGearButtonAvailability()

  def _updateGearButtonAvailability(self):
    inputs = [self.labelMapSelector.currentNode(), self.imageVolumeSelector.currentNode()]
    self.editorWidgetButton.checked = False
    self.editorWidgetButton.setEnabled(not any(i is None for i in inputs) and not self.quickSegmentationButton.checked)

  def onQuickSegmentationButtonToggled(self, enabled):
    self.updateSegmentationButtons()
    self.imageVolumeSelector.enabled = not enabled
    if enabled:
      self.setBackgroundToVolumeID(self.imageVolume)
      self.activateQuickSegmentationMode()
    self.deactivateUndoRedoButtons()

  def deactivateUndoRedoButtons(self):
    self.redoButton.setEnabled(False)
    self.undoButton.setEnabled(False)

  def onQuickSegmentationFinished(self):
    if not self.logic.isSegmentationValid():
      if not self.promptOnInvalidSegmentationDetected():
        self.invokeEvent(self.SegmentationCanceledEvent)
        self.deactivateQuickSegmentationMode(cancelled=True)
        self.quickSegmentationButton.checked = False
        return
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
    self.logic.addEventObserver(self.logic.UndoRedoEvent, self.updateUndoRedoButtons)
    self.markupNodeObserver = self.logic.inputMarkupNode.AddObserver(vtk.vtkCommand.ModifiedEvent,
                                                                     self.updateUndoRedoButtons)
    self.logic.clippingModelNode.SetDisplayVisibility(True)
    self.invokeEvent(self.SegmentationStartedEvent)
    self._updateGearButtonAvailability()

  def deactivateQuickSegmentationMode(self, cancelled=False):
    self.quickSegmentationButton.checked = False
    self.resetToRegularViewMode()
    self.logic.removeEventObserver(self.logic.UndoRedoEvent, self.updateUndoRedoButtons)
    if self.markupNodeObserver:
      self.markupNodeObserver = self.logic.inputMarkupNode.RemoveObserver(self.markupNodeObserver)
    self.logic.stopQuickSegmentationMode(cancelled)
    self._updateGearButtonAvailability()

  def updateUndoRedoButtons(self, observer=None, caller=None):
    self.redoButton.setEnabled(self.logic.redoPossible)
    self.undoButton.setEnabled(self.logic.undoPossible)

  def onCancelSegmentationButtonClicked(self):
    if slicer.util.confirmYesNoDisplay("Do you really want to cancel the segmentation process?",
                                       windowTitle="SliceTracker"):
      self.deactivateQuickSegmentationMode(cancelled=True)
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
    self._colorNode = getattr(self, "_colorNode",slicer.util.getNode('GenericAnatomyColors'))
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
    self.seriesNumber = None
    self.clippingModelNode = None
    self.clippingModelDisplayNode = None
    self.inputMarkupNode = None
    self.deletedMarkups = None
    self.outputLabelValue = outputLabelValue
    self.deletedMarkupPositions = []
    self.interactionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLInteractionNodeSingleton")

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
    self.placeFiducials()
    self.addInputMarkupNodeObserver()

  def stopQuickSegmentationMode(self, cancelled=False):
    self.interactionNode.SetCurrentInteractionMode(self.interactionNode.ViewTransform)
    self.removeInputMarkupNodeObserver()
    if cancelled:
      self.reset()

  def updateModel(self, caller=None, event=None):
    import VolumeClipWithModel
    clipLogic = VolumeClipWithModel.VolumeClipWithModelLogic()
    clipLogic.updateModelFromMarkup(self.inputMarkupNode, self.clippingModelNode)

  def onMarkupModified(self, caller, event):
    self.updateModel()
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
    self.createAndConfigureClippingModelDisplayNode()
    self.createNewFiducialNode()
    volumeClipPointsDisplayNode = self.setupDisplayNode()
    self.inputMarkupNode.SetAndObserveDisplayNodeID(volumeClipPointsDisplayNode.GetID())
    self.interactionNode.SetPlaceModePersistence(1)
    self.interactionNode.SetCurrentInteractionMode(self.interactionNode.Place)

  def createAndConfigureClippingModelDisplayNode(self):
    self.clippingModelNode = slicer.vtkMRMLModelNode()
    prefix = "{}-".format(self.seriesNumber) if self.seriesNumber else ""
    self.clippingModelNode.SetName('%sVolumeClip-MODEL'%prefix)
    slicer.mrmlScene.AddNode(self.clippingModelNode)

    self.clippingModelDisplayNode = slicer.vtkMRMLModelDisplayNode()
    self.clippingModelDisplayNode.SetSliceIntersectionThickness(3)
    # self.refreshViewNodeIDs
    self.clippingModelDisplayNode.SetColor(self.labelValueToRGB(self.outputLabelValue) if self.outputLabelValue
                                           else [0.200, 0.800, 0.000])
    self.clippingModelDisplayNode.BackfaceCullingOff()
    self.clippingModelDisplayNode.SliceIntersectionVisibilityOn()
    self.clippingModelDisplayNode.SetOpacity(0.3)
    slicer.mrmlScene.AddNode(self.clippingModelDisplayNode)
    self.clippingModelNode.SetAndObserveDisplayNodeID(self.clippingModelDisplayNode.GetID())

  def createNewFiducialNode(self):
    prefix = "{}-".format(self.seriesNumber) if self.seriesNumber else ""
    self.inputMarkupNode = slicer.mrmlScene.GetNodeByID(self.markupsLogic.AddNewFiducialNode())
    self.inputMarkupNode.SetName('%sVolumeClip-POINTS'%prefix)

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
    self.inputMarkupNode.RemoveMarkup(numberOfTargets-1)
    self.addInputMarkupNodeObserver()
    self.updateModel()
    self.invokeEvent(self.UndoRedoEvent)

  def redo(self):
    if not len(self.deletedMarkupPositions):
      return
    pos = self.deletedMarkupPositions.pop()
    self.removeInputMarkupNodeObserver()
    self.inputMarkupNode.AddFiducialFromArray(pos)
    self.addInputMarkupNodeObserver()
    self.updateModel()
    self.invokeEvent(self.UndoRedoEvent)

  def labelValueToRGB(self, labelValue, colorNode=None):
    colorNode = colorNode if colorNode else self.colorNode
    if colorNode:
      lut = colorNode.GetLookupTable()
      rgb = lut.GetTableValue(labelValue)
      return [rgb[0], rgb[1], rgb[2]]
    return None