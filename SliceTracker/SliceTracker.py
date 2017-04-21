import ast
import vtk
import logging

from SliceTrackerUtils.configuration import SliceTrackerConfiguration
from SliceTrackerUtils.constants import SliceTrackerConstants
from SliceTrackerUtils.session import SliceTrackerSession

from SliceTrackerUtils.steps.base import SliceTrackerStep
from SliceTrackerUtils.steps.overview import SliceTrackerOverviewStep
from SliceTrackerUtils.steps.zFrameRegistration import SliceTrackerZFrameRegistrationStep
from SliceTrackerUtils.steps.evaluation import SliceTrackerEvaluationStep
from SliceTrackerUtils.steps.segmentation import SliceTrackerSegmentationStep

from SlicerProstateUtils.buttons import *
from SlicerProstateUtils.constants import DICOMTAGS
from SlicerProstateUtils.decorators import logmethod
from SlicerProstateUtils.helpers import WatchBoxAttribute, DICOMBasedInformationWatchBox
from SlicerProstateUtils.mixins import ModuleWidgetMixin, ModuleLogicMixin
from SlicerProstateUtils.widgets import CustomStatusProgressbar
from slicer.ScriptedLoadableModule import *


class SliceTracker(ScriptedLoadableModule):

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "SliceTracker"
    self.parent.categories = ["Radiology"]
    self.parent.dependencies = ["SlicerProstate", "mpReview", "mpReviewPreprocessor"]
    self.parent.contributors = ["Christian Herz (SPL), Peter Behringer (SPL), Andriy Fedorov (SPL)"]
    self.parent.helpText = """ SliceTracker facilitates support of MRI-guided targeted prostate biopsy.
      See <a href=\"https://www.gitbook.com/book/slicerprostate/slicetracker/details\">the documentation</a> for
      details."""
    self.parent.acknowledgementText = """Surgical Planning Laboratory, Brigham and Women's Hospital, Harvard
                                          Medical School, Boston, USA This work was supported in part by the National
                                          Institutes of Health through grants U24 CA180918,
                                          R01 CA111288 and P41 EB015898."""


class SliceTrackerWidget(ModuleWidgetMixin, SliceTrackerConstants, ScriptedLoadableModuleWidget):

  def __init__(self, parent=None):
    ScriptedLoadableModuleWidget.__init__(self, parent)
    self.modulePath = os.path.dirname(slicer.util.modulePath(self.moduleName))
    SliceTrackerConfiguration(self.moduleName, os.path.join(self.modulePath, 'Resources', "default.cfg"))
    self.logic = SliceTrackerLogic()

    self.session = SliceTrackerSession()
    self.session.steps = []
    self.session.removeEventObservers()
    self.session.addEventObserver(self.session.CloseCaseEvent, lambda caller, event: self.cleanup())
    self.session.addEventObserver(SlicerProstateEvents.NewFileIndexedEvent, self.onNewFileIndexed)
    self.demoMode = False

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

    self.customStatusProgressBar = CustomStatusProgressbar()
    self.setupIcons()
    self.setupPatientWatchBox()
    self.setupViewSettingGroupBox()
    self.setupTabBarNavigation()
    self.setupConnections()
    self.setupSessionObservers()
    self.layout.addStretch(1)

  def setupIcons(self):
    self.settingsIcon = self.createIcon('icon-settings.png')
    self.textInfoIcon = self.createIcon('icon-text-info.png')

  def setupPatientWatchBox(self):
    WatchBoxAttribute.TRUNCATE_LENGTH = 20
    self.patientWatchBoxInformation = [WatchBoxAttribute('PatientName', 'Name: ', DICOMTAGS.PATIENT_NAME, masked=self.demoMode),
                                       WatchBoxAttribute('PatientID', 'PID: ', DICOMTAGS.PATIENT_ID, masked=self.demoMode),
                                       WatchBoxAttribute('DOB', 'DOB: ', DICOMTAGS.PATIENT_BIRTH_DATE, masked=self.demoMode),
                                       WatchBoxAttribute('StudyDate', 'Preop Date: ', DICOMTAGS.STUDY_DATE)]
    self.patientWatchBox = DICOMBasedInformationWatchBox(self.patientWatchBoxInformation, title="Patient Information",
                                                         columns=2)
    self.layout.addWidget(self.patientWatchBox)

    intraopWatchBoxInformation = [WatchBoxAttribute('CurrentSeries', 'Current Series: ', [DICOMTAGS.SERIES_NUMBER,
                                                                                          DICOMTAGS.SERIES_DESCRIPTION]),
                                  WatchBoxAttribute('StudyDate', 'Intraop Date: ', DICOMTAGS.STUDY_DATE)]
    self.intraopWatchBox = DICOMBasedInformationWatchBox(intraopWatchBoxInformation, columns=2)
    self.registrationDetailsButton = self.createButton("", icon=self.settingsIcon, styleSheet="border:none;",
                                                       maximumWidth=16)
    self.layout.addWidget(self.intraopWatchBox)

  def setupViewSettingGroupBox(self):
    iconSize = qt.QSize(24, 24)
    self.redOnlyLayoutButton = RedSliceLayoutButton()
    self.sideBySideLayoutButton = SideBySideLayoutButton()
    self.fourUpLayoutButton = FourUpLayoutButton()
    self.layoutButtons = [self.redOnlyLayoutButton, self.sideBySideLayoutButton, self.fourUpLayoutButton]
    self.crosshairButton = CrosshairButton()
    self.wlEffectsToolButton = WindowLevelEffectsButton()
    self.settingsButton = ModuleSettingsButton(self.moduleName)
    self.showAnnotationsButton = self.createButton("", icon=self.textInfoIcon, iconSize=iconSize, checkable=True, toolTip="Display annotations", checked=True)

    viewSettingButtons = [self.redOnlyLayoutButton, self.sideBySideLayoutButton, self.fourUpLayoutButton,
                          self.crosshairButton,   self.wlEffectsToolButton, self.settingsButton]

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
    self.tabWidget.addEventObserver(self.tabWidget.AvailableLayoutsChangedEvent, self.onAvailableLayoutsChanged)
    self.layout.addWidget(self.tabWidget)
    self.tabWidget.hideTabs()

  def setupConnections(self):
    self.showAnnotationsButton.connect('toggled(bool)', self.onShowAnnotationsToggled)

  def setupSessionObservers(self):
    self.session.addEventObserver(self.session.PreprocessingSuccessfulEvent, self.onSuccessfulPreProcessing)
    self.session.addEventObserver(self.session.CurrentSeriesChangedEvent, self.onCurrentSeriesChanged)

  def removeSessionObservers(self):
    self.session.removeEventObserver(self.session.PreprocessingSuccessfulEvent, self.onSuccessfulPreProcessing)
    self.session.removeEventObserver(self.session.CurrentSeriesChangedEvent, self.onCurrentSeriesChanged)

  def onSuccessfulPreProcessing(self, caller, event):
    dicomFileName = self.logic.getFileList(self.session.preopDICOMDirectory)[0]
    self.patientWatchBox.sourceFile = os.path.join(self.session.preopDICOMDirectory, dicomFileName)

  def onShowAnnotationsToggled(self, checked):
    allSliceAnnotations = self.sliceAnnotations[:]

  @vtk.calldata_type(vtk.VTK_STRING)
  def onNewFileIndexed(self, caller, event, callData):
    text, size, currentIndex = ast.literal_eval(callData)
    if not self.customStatusProgressBar.visible:
      self.customStatusProgressBar.show()
    self.customStatusProgressBar.maximum = size
    self.customStatusProgressBar.updateStatus(text, currentIndex)

  @vtk.calldata_type(vtk.VTK_STRING)
  def onCurrentSeriesChanged(self, caller, event, callData):
    self.intraopWatchBox.sourceFile = self.session.loadableList[callData][0] if callData else None

  @vtk.calldata_type(vtk.VTK_STRING)
  def onAvailableLayoutsChanged(self, caller, event, callData):
    layouts = ast.literal_eval(callData)
    for layoutButton in self.layoutButtons:
      layoutButton.enabled = layoutButton.LAYOUT in layouts

class SliceTrackerLogic(ModuleLogicMixin):

  def __init__(self):
    pass


class SliceTrackerTabWidget(qt.QTabWidget, ModuleWidgetMixin):

  AvailableLayoutsChangedEvent = SliceTrackerStep.AvailableLayoutsChangedEvent

  def __init__(self):
    super(SliceTrackerTabWidget, self).__init__()
    self.session = SliceTrackerSession()
    self._createTabs()
    self.currentChanged.connect(self.onCurrentTabChanged)
    self.onCurrentTabChanged(0)

  def hideTabs(self):
    self.tabBar().hide()

  def _createTabs(self):
    # TODO: cleanup on reload?
    for step in self.session.steps:
      logging.debug("Adding tab for %s step" % step.NAME)
      self.addTab(step, step.NAME)
      step.addEventObserver(step.ActivatedEvent, self.onStepActivated)
      step.addEventObserver(self.AvailableLayoutsChangedEvent, self.onStepAvailableLayoutChanged)

  @vtk.calldata_type(vtk.VTK_STRING)
  def onStepAvailableLayoutChanged(self, caller, event, callData):
    self.invokeEvent(self.AvailableLayoutsChangedEvent, callData)

  def onStepActivated(self, caller, event):
    name = caller.GetAttribute("Name")
    index = next((i for i, step in enumerate(self.session.steps) if step.NAME == name), None)
    if index is not None:
      self.setCurrentIndex(index)

  @logmethod(logging.DEBUG)
  def onCurrentTabChanged(self, index):
    for idx, step in enumerate(self.session.steps):
      if index != idx:
        if step.active:
          self.session.previousStep = step
        step.active = False
    self.session.steps[index].active = True


class SliceTrackerSlicelet(qt.QWidget, ModuleWidgetMixin):

  class MainWindow(qt.QWidget):

    def __init__(self, parent=None):
      qt.QWidget.__init__(self)
      self.objectName = "qSlicerAppMainWindow"
      self.setLayout(qt.QVBoxLayout())
      self.mainFrame = qt.QFrame()
      self.mainFrame.setLayout(qt.QHBoxLayout())

      self._statusBar = qt.QStatusBar()
      self._statusBar.setMaximumHeight(35)

      self.layout().addWidget(self.mainFrame)
      self.layout().addWidget(self._statusBar)

    def statusBar(self):
      self._statusBar = getattr(self, "_statusBar", None)
      if not self._statusBar:
        self._statusBar = qt.QStatusBar()
      return self._statusBar

  def __init__(self):
    qt.QWidget.__init__(self)

    print slicer.dicomDatabase

    self.mainWidget = SliceTrackerSlicelet.MainWindow()

    self.setupLayoutWidget()

    self.moduleFrame = qt.QWidget()
    self.moduleFrame.setLayout(qt.QVBoxLayout())
    self.widget = SliceTrackerWidget(self.moduleFrame)
    self.widget.setup()

    # TODO: resize self.widget.parent to minimum possible width

    self.scrollArea = qt.QScrollArea()
    self.scrollArea.setWidget(self.widget.parent)
    self.scrollArea.setWidgetResizable(True)
    self.scrollArea.setMinimumWidth(self.widget.parent.minimumSizeHint.width())

    self.splitter = qt.QSplitter()
    self.splitter.setOrientation(qt.Qt.Horizontal)
    self.splitter.addWidget(self.scrollArea)
    self.splitter.addWidget(self.layoutWidget)
    self.splitter.splitterMoved.connect(self.onSplitterMoved)

    self.splitter.setStretchFactor(0,0)
    self.splitter.setStretchFactor(1,1)
    self.splitter.handle(1).installEventFilter(self)

    self.mainWidget.mainFrame.layout().addWidget(self.splitter)
    self.mainWidget.show()

  def setupLayoutWidget(self):
    self.layoutWidget = qt.QWidget()
    self.layoutWidget.setLayout(qt.QHBoxLayout())
    layoutWidget = slicer.qMRMLLayoutWidget()
    layoutManager = slicer.qSlicerLayoutManager()
    layoutManager.setMRMLScene(slicer.mrmlScene)
    layoutManager.setScriptedDisplayableManagerDirectory(slicer.app.slicerHome + "/bin/Python/mrmlDisplayableManager")
    layoutWidget.setLayoutManager(layoutManager)
    slicer.app.setLayoutManager(layoutManager)
    layoutWidget.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView)
    self.layoutWidget.layout().addWidget(layoutWidget)

  def eventFilter(self, obj, event):
    if event.type() == qt.QEvent.MouseButtonDblClick:
      self.onSplitterClick()

  def onSplitterMoved(self, pos, index):
    vScroll = self.scrollArea.verticalScrollBar()
    print self.moduleFrame.width, self.widget.parent.width, self.scrollArea.width, vScroll.width
    vScrollbarWidth = 4 if not vScroll.isVisible() else vScroll.width + 4 # TODO: find out, what is 4px wide
    if self.scrollArea.minimumWidth != self.widget.parent.minimumSizeHint.width() + vScrollbarWidth:
      self.scrollArea.setMinimumWidth(self.widget.parent.minimumSizeHint.width() + vScrollbarWidth)

  def onSplitterClick(self):
    if self.splitter.sizes()[0] > 0:
      self.splitter.setSizes([0, self.splitter.sizes()[1]])
    else:
      minimumWidth = self.widget.parent.minimumSizeHint.width()
      self.splitter.setSizes([minimumWidth, self.splitter.sizes()[1]-minimumWidth])


if __name__ == "SliceTrackerSlicelet":
  import sys
  print( sys.argv )

  slicelet = SliceTrackerSlicelet()
