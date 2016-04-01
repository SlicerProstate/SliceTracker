import vtk, qt, slicer
from slicer.ScriptedLoadableModule import *
from SliceTrackerUtils.mixins import ModuleLogicMixin, ModuleWidgetMixin
from Editor import EditorWidget
import EditorLib
import os
from SliceTrackerUtils.ZFrameRegistration import ZFrameRegistration


class SliceTrackerZFrameRegistration(ScriptedLoadableModule):

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "SliceTracker ZFrame Registration"
    self.parent.categories = ["Radiology"]
    self.parent.dependencies = []
    self.parent.contributors = ["Christian Herz (SPL), Andriy Fedorov (SPL)"]
    self.parent.helpText = """  """
    self.parent.acknowledgementText = """Surgical Planning Laboratory, Brigham and Women's Hospital, Harvard
                                          Medical School, Boston, USA This work was supported in part by the National
                                          Institutes of Health through grants U24 CA180918,
                                          R01 CA111288 and P41 EB015898."""
    self.parent = parent

    try:
      slicer.selfTests
    except AttributeError:
      slicer.selfTests = {}
    slicer.selfTests['SliceTrackerZFrameRegistration'] = self.runTest

  def runTest(self):
    tester = SliceTrackerZFrameRegistration()
    tester.runTest()


class SliceTrackerZFrameRegistrationWidget(ScriptedLoadableModuleWidget, ModuleWidgetMixin):

  ZFRAME_MODEL_PATH = 'Resources/zframe/zframe-model.vtk'
  ZFRAME_MODEL_NAME = 'ZFrameModel'

  def __init__(self, parent=None):
    ScriptedLoadableModuleWidget.__init__(self, parent)
    self.logic = SliceTrackerZFrameRegistrationLogic()

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    self.setupSliceWidget()
    self.tag = None
    self.zFrameModelNode = None

    self.registrationGroupBox = qt.QGroupBox()
    self.registrationGroupBoxLayout = qt.QFormLayout()
    self.registrationGroupBox.setLayout(self.registrationGroupBoxLayout)
    self.zFrameTemplateVolumeSelector = self.createComboBox(nodeTypes=["vtkMRMLScalarVolumeNode", ""], showChildNodeTypes=False,
                                                            selectNodeUponCreation=True, toolTip="Pick algorithm input.")
    self.applyRegistrationButton = self.createButton("Run Registration")
    self.registrationGroupBoxLayout.addRow("ZFrame template: ", self.zFrameTemplateVolumeSelector)
    self.registrationGroupBoxLayout.addRow(self.applyRegistrationButton)
    self.layout.addWidget(self.registrationGroupBox)
    self.layout.addStretch()
    self.setupConnections()
    self.setupEditorWidget()
    self.loadZFrameModel()

  def loadZFrameModel(self):
    collection = slicer.mrmlScene.GetNodesByName(self.ZFRAME_MODEL_NAME)
    for index in range(collection.GetNumberOfItems()):
      slicer.mrmlScene.RemoveNode(collection.GetItemAsObject(index))
    self.modulePath = os.path.dirname(slicer.util.modulePath(self.moduleName))
    zFrameModelPath = os.path.join(self.modulePath, self.ZFRAME_MODEL_PATH)
    if not self.zFrameModelNode:
      _, self.zFrameModelNode = slicer.util.loadModel(zFrameModelPath, returnNode=True)
      self.zFrameModelNode.SetName(self.ZFRAME_MODEL_NAME)
      slicer.mrmlScene.AddNode(self.zFrameModelNode)
      modelDisplayNode = self.zFrameModelNode.GetDisplayNode()
      modelDisplayNode.SetColor(1, 1, 0)

  def setupSliceWidget(self, name):
    self.redWidget = self.layoutManager.sliceWidget("Red")
    self.redCompositeNode = self.redWidget.mrmlSliceCompositeNode()
    self.redSliceView = self.redWidget.sliceView()
    self.redSliceLogic = self.redWidget.sliceLogic()
    self.redSliceNode = self.redSliceLogic.GetSliceNode()

  def setupEditorWidget(self):
    self.editorWidgetParent = slicer.qMRMLWidget()
    self.editorWidgetParent.setLayout(qt.QVBoxLayout())
    self.editorWidgetParent.setMRMLScene(slicer.mrmlScene)
    self.editUtil = EditorLib.EditUtil.EditUtil()
    self.editorWidget = EditorWidget(parent=self.editorWidgetParent, showVolumesFrame=False)
    self.editorWidget.setup()
    self.editorParameterNode = self.editUtil.getParameterNode()

  def setupConnections(self):
    self.applyRegistrationButton.clicked.connect(self.runRegistration)
    self.zFrameTemplateVolumeSelector.connect('currentNodeChanged(bool)', self.loadVolumeAndEnableEditor)

  def processEvent(self, caller=None, event=None):
    if event == "LeftButtonReleaseEvent":
      interactor = self.redSliceView.interactorStyle().GetInteractor()
      xy = interactor.GetEventPosition()
      interactor.RemoveObserver(self.tag)
      self.tag = None
      self.onCenterPointSet(xy)

  def loadVolumeAndEnableEditor(self):
    zFrameTemplateVolume = self.zFrameTemplateVolumeSelector.currentNode()
    self.redCompositeNode.SetBackgroundVolumeID(zFrameTemplateVolume.GetID())
    interactor = self.redSliceView.interactorStyle().GetInteractor()
    if self.tag:
      interactor.RemoveObserver(self.tag)
    self.tag = interactor.AddObserver(vtk.vtkCommand.LeftButtonReleaseEvent, self.processEvent, 1.0)

  def onCenterPointSet(self, xy):
    import vtk.util.numpy_support as vnp

    zFrameTemplateVolume = self.zFrameTemplateVolumeSelector.currentNode()
    volumesLogic = slicer.modules.volumes.logic()
    zFrameTemplateMask = volumesLogic.CreateLabelVolume(slicer.mrmlScene, zFrameTemplateVolume, 'zFrameTemplateMask')

    imageDataWorkingCopy = vtk.vtkImageData()
    imageDataWorkingCopy.DeepCopy(zFrameTemplateMask.GetImageData())
    newLabelNodeImage=vtk.vtkImageData()
    newLabelNodeImage.AllocateScalars(vtk.VTK_SHORT, 1)
    newLabelNodeImage.SetExtent(zFrameTemplateMask.GetImageData().GetExtent())
    numpyArray = vnp.vtk_to_numpy(imageDataWorkingCopy.GetPointData().GetScalars()).reshape(imageDataWorkingCopy.GetDimensions()).transpose(2,1,0)
    numpyArray[6:10,70:185,65:190].fill(1)
    spacing = imageDataWorkingCopy.GetSpacing()
    vtk_data = vnp.numpy_to_vtk(num_array=numpyArray.ravel(), deep=True, array_type=vtk.VTK_SHORT)
    newLabelNodeImage.GetPointData().SetScalars(vtk_data)
    dims = numpyArray.shape
    newLabelNodeImage.SetDimensions(dims[2], dims[1], dims[0])
    newLabelNodeImage.SetOrigin(0,0,0)
    newLabelNodeImage.SetSpacing(spacing[0], spacing[1], spacing[2])
    zFrameTemplateMask.SetAndObserveImageData(newLabelNodeImage)
    # update the default label map to the generic anatomy colors
    labelDisplayNode = zFrameTemplateMask.GetDisplayNode()
    labelColorTable = slicer.util.getNode('GenericAnatomyColors')
    labelDisplayNode.SetAndObserveColorNodeID(labelColorTable.GetID())

    self.redCompositeNode.SetBackgroundVolumeID(zFrameTemplateVolume.GetID())
    self.redCompositeNode.SetLabelVolumeID(zFrameTemplateMask.GetID())
    self.redCompositeNode.SetLabelOpacity(0.6)

    self.maskedVolume = self.createMaskedVolume(zFrameTemplateVolume, zFrameTemplateMask)

  def createMaskedVolume(self, inputVolume, labelVolume):
    maskedVolume = slicer.vtkMRMLScalarVolumeNode()
    maskedVolume.SetName("maskedTemplateVolume")
    slicer.mrmlScene.AddNode(maskedVolume)
    params = {'InputVolume': inputVolume, 'MaskVolume': labelVolume, 'OutputVolume': maskedVolume}
    slicer.cli.run(slicer.modules.maskscalarvolume, None, params, wait_for_completion=True)
    return maskedVolume

  def isRegistrationPossible(self):
    return False

  def runRegistration(self):
    registration = ZFrameRegistration(self.maskedVolume)
    registration.runRegistration()
    self.zFrameModelNode.SetAndObserveTransformNodeID(registration.outputTransform.GetID())

class SliceTrackerZFrameRegistrationLogic(ScriptedLoadableModuleLogic, ModuleLogicMixin):

  def __init__(self):
    ScriptedLoadableModuleLogic.__init__(self)
    self.volumesLogic = slicer.modules.volumes.logic()
    self.markupsLogic = slicer.modules.markups.logic()
    self.registrationResult = None

  def run(self, parameterNode, progressCallback=None):
    pass

