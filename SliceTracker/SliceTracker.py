import ast
import logging

import ctk
import qt
import vtk

from SliceTrackerUtils.configuration import SliceTrackerConfiguration
from SliceTrackerUtils.constants import SliceTrackerConstants
from SliceTrackerUtils.session import SliceTrackerSession
from SliceTrackerUtils.steps.base import SliceTrackerStepLogic, SliceTrackerStep
from SliceTrackerUtils.steps.zFrameRegistration import SliceTrackerZFrameRegistrationStep
from SliceTrackerUtils.steps.overview import SliceTrackerOverviewStep
from SlicerProstateUtils.buttons import *
from SlicerProstateUtils.constants import DICOMTAGS
from SlicerProstateUtils.decorators import logmethod
from SlicerProstateUtils.helpers import TargetCreationWidget
from SlicerProstateUtils.helpers import WatchBoxAttribute, DICOMBasedInformationWatchBox
from SlicerProstateUtils.mixins import ModuleWidgetMixin
from slicer.ScriptedLoadableModule import *


class SliceTracker(ScriptedLoadableModule):

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "SliceTracker"
    self.parent.categories = ["Radiology"]
    self.parent.dependencies = ["SlicerProstate", "mpReview", "mpReviewPreprocessor"]
    self.parent.contributors = ["Christian Herz (SPL), Peter Behringer (SPL), Andriy Fedorov (SPL)"]
    self.parent.helpText = """ SliceTracker facilitates support of MRI-guided targeted prostate biopsy. See <a href=\"https://www.gitbook.com/read/book/fedorov/slicetracker\">the documentation</a> for details."""
    self.parent.acknowledgementText = """Surgical Planning Laboratory, Brigham and Women's Hospital, Harvard
                                          Medical School, Boston, USA This work was supported in part by the National
                                          Institutes of Health through grants U24 CA180918,
                                          R01 CA111288 and P41 EB015898."""


class SliceTrackerWidget(ModuleWidgetMixin, SliceTrackerConstants, ScriptedLoadableModuleWidget):

  def __init__(self, parent=None):
    ScriptedLoadableModuleWidget.__init__(self, parent)
    self.modulePath = os.path.dirname(slicer.util.modulePath(self.moduleName))
    SliceTrackerConfiguration(self.moduleName, os.path.join(self.modulePath, 'Resources', "default.cfg"))
    self.logic = None
    #   TODO set logic instances here

    self.session = SliceTrackerSession()
    self.session.steps = []
    self.session.removeEventObservers()
    self.session.addEventObserver(self.session.CloseCaseEvent, lambda caller, event: self.cleanup())
    self.session.addEventObserver(SlicerProstateEvents.NewFileIndexedEvent, self.onNewFileIndexed)
    self.demoMode = False

    slicer.app.connect('aboutToQuit()', self.onSlicerQuits)

  def onSlicerQuits(self):
    if self.session.isRunning():
      if slicer.util.confirmYesNoDisplay("Case is still running! Slicer is about to be closed. Do you want to mark the "
                                         "current case as completed? Otherwise it will only be closed and can be "
                                         "resumed at a later time"):
        self.session.complete()
      else:
        self.session.close(save=True)
    self.cleanup()

  def enter(self):
    if not slicer.dicomDatabase:
      slicer.util.errorDisplay("Slicer DICOMDatabase was not found. In order to be able to use SliceTracker, you will "
                               "need to set a proper location for the Slicer DICOMDatabase.")
    self.layout.parent().enabled = slicer.dicomDatabase is not None

  def exit(self):
    pass

  def onReload(self):
    ScriptedLoadableModuleWidget.onReload(self)

  @logmethod(logging.DEBUG)
  def cleanup(self):
    ScriptedLoadableModuleWidget.cleanup(self)
    self.patientWatchBox.sourceFile = None
    self.intraopWatchBox.sourceFile = None

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    for step in [SliceTrackerOverviewStep, SliceTrackerZFrameRegistrationStep,
                 SliceTrackerSegmentationStep, SliceTrackerEvaluationStep]:
      self.session.registerStep(step())

    self.customStatusProgressBar = self.getOrCreateCustomProgressBar()
    self.setupIcons()
    self.setupPatientWatchBox()
    self.setupViewSettingGroupBox()
    self.setupTabBarNavigation()
    self.setupConnections()
    self.layout.addStretch(1)

  def setupIcons(self):
    self.settingsIcon = self.createIcon('icon-settings.png')
    self.textInfoIcon = self.createIcon('icon-text-info.png')

  def setupPatientWatchBox(self):
    self.patientWatchBoxInformation = [WatchBoxAttribute('PatientID', 'Patient ID: ', DICOMTAGS.PATIENT_ID, masked=self.demoMode),
                                       WatchBoxAttribute('PatientName', 'Patient Name: ', DICOMTAGS.PATIENT_NAME, masked=self.demoMode),
                                       WatchBoxAttribute('DOB', 'Date of Birth: ', DICOMTAGS.PATIENT_BIRTH_DATE, masked=self.demoMode),
                                       WatchBoxAttribute('StudyDate', 'Preop Study Date: ', DICOMTAGS.STUDY_DATE)]
    self.patientWatchBox = DICOMBasedInformationWatchBox(self.patientWatchBoxInformation)
    self.layout.addWidget(self.patientWatchBox)

    intraopWatchBoxInformation = [WatchBoxAttribute('StudyDate', 'Intraop Study Date: ', DICOMTAGS.STUDY_DATE),
                                  WatchBoxAttribute('CurrentSeries', 'Current Series: ', [DICOMTAGS.SERIES_NUMBER,
                                                                                          DICOMTAGS.SERIES_DESCRIPTION])]
    self.intraopWatchBox = DICOMBasedInformationWatchBox(intraopWatchBoxInformation)
    self.registrationDetailsButton = self.createButton("", icon=self.settingsIcon, styleSheet="border:none;",
                                                       maximumWidth=16)
    self.layout.addWidget(self.intraopWatchBox)

  def setupViewSettingGroupBox(self):
    iconSize = qt.QSize(24, 24)
    self.redOnlyLayoutButton = RedSliceLayoutButton()
    self.sideBySideLayoutButton = SideBySideLayoutButton()
    self.fourUpLayoutButton = FourUpLayoutButton()
    self.crosshairButton = CrosshairButton()
    self.wlEffectsToolButton = WindowLevelEffectsButton()
    self.settingsButton = ModuleSettingsButton(self.moduleName)
    self.showAnnotationsButton = self.createButton("", icon=self.textInfoIcon, iconSize=iconSize, checkable=True, toolTip="Display annotations", checked=True)

    viewSettingButtons = [self.redOnlyLayoutButton, self.sideBySideLayoutButton, self.fourUpLayoutButton,
                          self.showAnnotationsButton, self.crosshairButton,   self.wlEffectsToolButton,
                          self.settingsButton]

    for step in self.session.steps:
      viewSettingButtons += step.viewSettingButtons

    self.layout.addWidget(self.createHLayout(viewSettingButtons))

    self.resetViewSettingButtons()

  def resetViewSettingButtons(self):
    for step in self.session.steps:
      step.resetViewSettingButtons()
    self.wlEffectsToolButton.checked = False
    self.crosshairButton.checked = False

  def setupTabBarNavigation(self):
    self.tabWidget = SliceTrackerTabWidget()
    self.layout.addWidget(self.tabWidget)

    # TODO
    # self.tabWidget.hideTabs()

  def setupConnections(self):
    self.showAnnotationsButton.connect('toggled(bool)', self.onShowAnnotationsToggled)

  def onShowAnnotationsToggled(self, checked):
    allSliceAnnotations = self.sliceAnnotations[:]

  @vtk.calldata_type(vtk.VTK_STRING)
  def onNewFileIndexed(self, caller, event, callData):
    text, size, currentIndex = ast.literal_eval(callData)
    if not self.customStatusProgressBar.visible:
      self.customStatusProgressBar.show()
    self.customStatusProgressBar.maximum = size
    self.customStatusProgressBar.updateStatus(text, currentIndex)


class SliceTrackerTabWidget(qt.QTabWidget):

  def __init__(self):
    super(SliceTrackerTabWidget, self).__init__()
    self.session = SliceTrackerSession()
    self._createTabs()
    self.currentChanged.connect(self.onCurrentTabChanged)
    self.onCurrentTabChanged(0)

  def hideTabs(self):
    self.tabBar().hide()

  def _createTabs(self):
    for step in self.session.steps:
      logging.debug("Adding tab for %s step" % step.NAME)
      self.addTab(step, step.NAME)
      step.addEventObserver(step.ActivatedEvent, self.onStepActivated)

  def onStepActivated(self, caller, event):
    name = caller.GetAttribute("Name")
    index = next((i for i, step in enumerate(self.session.steps) if step.NAME == name), None)
    if index is not None:
      self.setCurrentIndex(index)

  def onCurrentTabChanged(self, index):
    map(lambda step: setattr(step, "active", False), self.session.steps)
    self.session.steps[index].active = True


import EditorLib
from Editor import EditorWidget
from VolumeClipToLabel import VolumeClipToLabelWidget


class SliceTrackerSegmentationStepLogic(SliceTrackerStepLogic):

  def __init__(self):
    super(SliceTrackerSegmentationStepLogic, self).__init__()

  def cleanup(self):
    pass


class SliceTrackerSegmentationStep(SliceTrackerStep):

  NAME = "Segmentation"
  LogicClass = SliceTrackerSegmentationStepLogic

  def __init__(self):
    self.modulePath = os.path.dirname(slicer.util.modulePath(self.MODULE_NAME)).replace(".py", "")
    super(SliceTrackerSegmentationStep, self).__init__()

  def setup(self):
    self.setupIcons()
    try:
      import VolumeClipWithModel
    except ImportError:
      return slicer.util.warningDisplay("Error: Could not find extension VolumeClip. Open Slicer Extension Manager and "
                                        "install VolumeClip.", "Missing Extension")

    iconSize = qt.QSize(24, 24)

    self.volumeClipGroupBox = qt.QWidget()
    self.volumeClipGroupBoxLayout = qt.QVBoxLayout()
    self.volumeClipGroupBox.setLayout(self.volumeClipGroupBoxLayout)

    self.volumeClipToLabelWidget = VolumeClipToLabelWidget(self.volumeClipGroupBox)
    self.volumeClipToLabelWidget.setup()
    if qt.QSettings().value('Developer/DeveloperMode').lower() == 'true':
      self.volumeClipToLabelWidget.reloadCollapsibleButton.hide()
    self.volumeClipToLabelWidget.selectorsGroupBox.hide()
    self.volumeClipToLabelWidget.colorGroupBox.hide()

    # TODO!!!!
    # self.volumeClipToLabelWidget.logic.colorNode = self.logic.mpReviewColorNode
    # self.volumeClipToLabelWidget.onColorSelected(self.logic.segmentedLabelValue)

    self.applyRegistrationButton = self.createButton("Apply Registration", icon=self.greenCheckIcon, iconSize=iconSize,
                                                     toolTip="Run Registration.")
    self.applyRegistrationButton.setFixedHeight(45)

    self.editorWidgetButton = self.createButton("", icon=self.settingsIcon, toolTip="Show Label Editor",
                                                enabled=False, iconSize=iconSize)

    self.setupEditorWidget()
    self.segmentationGroupBox = qt.QGroupBox()
    self.segmentationGroupBoxLayout = qt.QGridLayout()
    self.segmentationGroupBox.setLayout(self.segmentationGroupBoxLayout)
    self.volumeClipToLabelWidget.segmentationButtons.layout().addWidget(self.editorWidgetButton)
    self.segmentationGroupBoxLayout.addWidget(self.volumeClipGroupBox, 0, 0)
    self.segmentationGroupBoxLayout.addWidget(self.editorWidgetParent, 1, 0)
    self.segmentationGroupBoxLayout.addWidget(self.applyRegistrationButton, 2, 0)
    self.segmentationGroupBoxLayout.setRowStretch(3, 1)
    self.layout().addWidget(self.segmentationGroupBox)
    self.editorWidgetParent.hide()

    # TODO: control visibility of target settings table
    self.setupTargetingStepUIElements()

  def setupIcons(self):
    self.greenCheckIcon = self.createIcon('icon-greenCheck.png')
    self.settingsIcon = self.createIcon('icon-settings.png')

  def setupEditorWidget(self):
    self.editorWidgetParent = slicer.qMRMLWidget()
    self.editorWidgetParent.setLayout(qt.QVBoxLayout())
    self.editorWidgetParent.setMRMLScene(slicer.mrmlScene)
    self.editUtil = EditorLib.EditUtil.EditUtil()
    self.editorWidget = EditorWidget(parent=self.editorWidgetParent, showVolumesFrame=False)
    self.editorWidget.setup()
    self.editorParameterNode = self.editUtil.getParameterNode()

  def setupTargetingStepUIElements(self):
    self.targetingGroupBox = qt.QGroupBox()
    self.targetingGroupBoxLayout = qt.QFormLayout()
    self.targetingGroupBox.setLayout(self.targetingGroupBoxLayout)

    self.fiducialsWidget = TargetCreationWidget(self.targetingGroupBoxLayout)
    self.fiducialsWidget.addEventObserver(vtk.vtkCommand.ModifiedEvent, self.onTargetListModified)
    self.finishTargetingStepButton = self.createButton("Done setting targets", enabled=True,
                                                       toolTip="Click this button to continue after setting targets")

    self.targetingGroupBoxLayout.addRow(self.finishTargetingStepButton)
    self.layout().addWidget(self.targetingGroupBox)

  def setupConnections(self):
    super(SliceTrackerSegmentationStep, self).setupConnections()
    self.fiducialsWidget.addEventObserver(vtk.vtkCommand.ModifiedEvent, self.onTargetListModified)

  def onTargetListModified(self, caller, event):
    self.finishTargetingStepButton.enabled = self.fiducialsWidget.currentNode is not None and \
                                             self.fiducialsWidget.currentNode.GetNumberOfFiducials()


class SliceTrackerEvaluationStepLogic(SliceTrackerStepLogic):

  def __init__(self):
    super(SliceTrackerEvaluationStepLogic, self).__init__()

  def cleanup(self):
    pass



class SliceTrackerEvaluationStep(SliceTrackerStep):

  NAME = "Evaluation"
  LogicClass = SliceTrackerEvaluationStepLogic

  def __init__(self):
    self.modulePath = os.path.dirname(slicer.util.modulePath(self.MODULE_NAME)).replace(".py", "")
    super(SliceTrackerEvaluationStep, self).__init__()

  def setup(self):
    self.setupIcons()
    self.registrationEvaluationGroupBox = qt.QGroupBox()
    self.registrationEvaluationGroupBoxLayout = qt.QGridLayout()
    self.registrationEvaluationGroupBox.setLayout(self.registrationEvaluationGroupBoxLayout)

    self.setupRegistrationResultsGroupBox()
    self.setupTargetsTable()
    self.setupRegistrationValidationButtons()
    self.registrationEvaluationGroupBoxLayout.addWidget(self.registrationResultsGroupBox, 3, 0)
    self.registrationEvaluationGroupBoxLayout.addWidget(self.targetTable, 4, 0)  # factor out the table since it is used in both Overview and evaluation step
    self.registrationEvaluationGroupBoxLayout.addWidget(self.registrationEvaluationButtonsGroupBox, 5, 0)
    self.registrationEvaluationGroupBoxLayout.setRowStretch(6, 1)
    self.layout().addWidget(self.registrationEvaluationGroupBox)

  def setupIcons(self):
    self.revealCursorIcon = self.createIcon('icon-revealCursor.png')

  def setupRegistrationValidationButtons(self):
    self.approveRegistrationResultButton = self.createButton("Approve", toolTip="Approve")
    self.retryRegistrationButton = self.createButton("Retry", toolTip="Retry")
    self.rejectRegistrationResultButton = self.createButton("Reject", toolTip="Reject")
    self.registrationEvaluationButtonsGroupBox = self.createHLayout([self.retryRegistrationButton,
                                                                     self.approveRegistrationResultButton,
                                                                     self.rejectRegistrationResultButton])
    self.registrationEvaluationButtonsGroupBox.enabled = False

  def setupRegistrationResultsGroupBox(self):

    self.registrationResultsGroupBox = qt.QGroupBox("Registration Results")
    self.registrationResultsGroupBoxLayout = qt.QFormLayout()
    self.registrationResultsGroupBox.setLayout(self.registrationResultsGroupBoxLayout)

    self.resultSelector = ctk.ctkComboBox()
    self.registrationResultsGroupBoxLayout.addWidget(self.resultSelector)

    self.rigidResultButton = self.createButton('Rigid', checkable=True, name='rigid')
    self.affineResultButton = self.createButton('Affine', checkable=True, name='affine')
    self.bSplineResultButton = self.createButton('BSpline', checkable=True, name='bSpline')

    self.registrationButtonGroup = qt.QButtonGroup()
    self.registrationButtonGroup.addButton(self.rigidResultButton, 1)
    self.registrationButtonGroup.addButton(self.affineResultButton, 2)
    self.registrationButtonGroup.addButton(self.bSplineResultButton, 3)

    self.registrationTypesGroupBox = qt.QGroupBox("Type")
    self.registrationTypesGroupBoxLayout = qt.QFormLayout(self.registrationTypesGroupBox)
    self.registrationTypesGroupBoxLayout.addWidget(self.createVLayout([self.rigidResultButton,
                                                                       self.affineResultButton,
                                                                       self.bSplineResultButton]))
    self.setupVisualEffectsUIElements()

    self.registrationResultsGroupBoxLayout.addWidget(self.createHLayout([self.registrationTypesGroupBox,
                                                                         self.visualEffectsGroupBox]))

  def setupTargetsTable(self):
    self.targetTable = qt.QTableView()
    self.targetTable.setSelectionBehavior(qt.QTableView.SelectItems)
    self.setTargetTableSizeConstraints()
    self.targetTable.verticalHeader().hide()
    self.targetTable.minimumHeight = 150
    self.targetTable.setStyleSheet("QTableView::item:selected{background-color: #ff7f7f; color: black};")

  def setTargetTableSizeConstraints(self):
    self.targetTable.horizontalHeader().setResizeMode(qt.QHeaderView.Stretch)
    self.targetTable.horizontalHeader().setResizeMode(0, qt.QHeaderView.Fixed)
    self.targetTable.horizontalHeader().setResizeMode(1, qt.QHeaderView.Stretch)
    self.targetTable.horizontalHeader().setResizeMode(2, qt.QHeaderView.ResizeToContents)
    self.targetTable.horizontalHeader().setResizeMode(3, qt.QHeaderView.ResizeToContents)

  def setupVisualEffectsUIElements(self):
    self.opacitySpinBox = qt.QDoubleSpinBox()
    self.opacitySpinBox.minimum = 0
    self.opacitySpinBox.maximum = 1.0
    self.opacitySpinBox.value = 0
    self.opacitySpinBox.singleStep = 0.05

    self.opacitySliderPopup = ctk.ctkPopupWidget(self.opacitySpinBox)
    popupLayout = qt.QHBoxLayout(self.opacitySliderPopup)
    self.opacitySlider = ctk.ctkDoubleSlider(self.opacitySliderPopup)
    self.opacitySlider.orientation = qt.Qt.Horizontal
    self.opacitySlider.minimum = 0
    self.opacitySlider.maximum = 1.0
    self.opacitySlider.value = 0
    self.opacitySlider.singleStep = 0.05

    popupLayout.addWidget(self.opacitySlider)
    self.opacitySliderPopup.verticalDirection = ctk.ctkBasePopupWidget.TopToBottom
    self.opacitySliderPopup.animationEffect = ctk.ctkBasePopupWidget.FadeEffect
    self.opacitySliderPopup.orientation = qt.Qt.Horizontal
    self.opacitySliderPopup.easingCurve = qt.QEasingCurve.OutQuart
    self.opacitySliderPopup.effectDuration = 100

    self.rockCount = 0
    self.rockTimer = qt.QTimer()
    self.rockTimer.setInterval(50)
    self.rockCheckBox = qt.QCheckBox("Rock")
    self.rockCheckBox.checked = False

    self.flickerTimer = qt.QTimer()
    self.flickerTimer.setInterval(400)
    self.flickerCheckBox = qt.QCheckBox("Flicker")
    self.flickerCheckBox.checked = False

    self.animaHolderLayout = self.createHLayout([self.rockCheckBox, self.flickerCheckBox])
    self.visualEffectsGroupBox = qt.QGroupBox("Visual Effects")
    self.visualEffectsGroupBoxLayout = qt.QFormLayout(self.visualEffectsGroupBox)
    self.revealCursorButton = self.createButton("", icon=self.revealCursorIcon, checkable=True,
                                                enabled=False, toolTip="Use reveal cursor")
    slider = self.createHLayout([self.opacitySpinBox, self.animaHolderLayout])
    self.visualEffectsGroupBoxLayout.addWidget(self.createVLayout([slider, self.revealCursorButton]))