import ast
import logging

import ctk
import qt
import vtk

from SliceTrackerUtils.steps.zFrameRegistration import SliceTrackerZFrameRegistrationStep
from SliceTrackerUtils.configuration import SliceTrackerConfiguration
from SliceTrackerUtils.constants import SliceTrackerConstants
from SliceTrackerUtils.exceptions import PreProcessedDataError
from SliceTrackerUtils.session import SliceTrackerSession
from SliceTrackerUtils.sessionData import RegistrationResult
from SliceTrackerUtils.steps.base import SliceTrackerStepLogic, SliceTrackerStep
from SliceTrackerUtils.steps.training import SliceTrackerTrainingStep
from SlicerProstateUtils.buttons import *
from SlicerProstateUtils.constants import DICOMTAGS, COLOR
from SlicerProstateUtils.decorators import logmethod, onReturnProcessEvents
from SlicerProstateUtils.helpers import TargetCreationWidget, IncomingDataMessageBox
from SlicerProstateUtils.helpers import WatchBoxAttribute, BasicInformationWatchBox, DICOMBasedInformationWatchBox
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

from SliceTrackerUtils.helpers import NewCaseSelectionNameWidget


class SliceTrackerOverViewStepLogic(SliceTrackerStepLogic):

  def __init__(self):
    super(SliceTrackerOverViewStepLogic, self).__init__()
    self.scalarVolumePlugin = slicer.modules.dicomPlugins['DICOMScalarVolumePlugin']()

  def cleanup(self):
    pass

  def isTrackingPossible(self, series):
    if self.session.data.completed:
      return False
    if self.isInGeneralTrackable(series) and self.resultHasNotBeenProcessed(series):
      if self.getSetting("NEEDLE_IMAGE") in series:
        return self.session.data.getMostRecentApprovedCoverProstateRegistration() or not self.session.data.usePreopData
      elif self.getSetting("COVER_PROSTATE") in series:
        return self.session.zFrameRegistrationSuccessful
      elif self.getSetting("COVER_TEMPLATE") in series:
        return not self.session.zFrameRegistrationSuccessful # TODO: Think about this
    return False

  def isInGeneralTrackable(self, series):
    return self.isAnyListItemInString(series, [self.getSetting("COVER_TEMPLATE"),
                                               self.getSetting("COVER_PROSTATE"),
                                               self.getSetting("NEEDLE_IMAGE")])

  def isAnyListItemInString(self, string, listItem):
    return any(item in string for item in listItem)

  def resultHasNotBeenProcessed(self, series):
    return not (self.session.data.registrationResultWasApproved(series) or
                self.session.data.registrationResultWasSkipped(series) or
                self.session.data.registrationResultWasRejected(series))


class SliceTrackerOverviewStep(SliceTrackerStep):

  NAME = "Overview"
  LogicClass = SliceTrackerOverViewStepLogic

  @property
  def caseRootDir(self):
    return self.casesRootDirectoryButton.directory

  @caseRootDir.setter
  def caseRootDir(self, path):
    try:
      exists = os.path.exists(path)
    except TypeError:
      exists = False
    self.setSetting('CasesRootLocation', path if exists else None)
    self.casesRootDirectoryButton.text = self.truncatePath(path) if exists else "Choose output directory"
    self.casesRootDirectoryButton.toolTip = path
    self.openCaseButton.enabled = exists
    self.createNewCaseButton.enabled = exists

  def __init__(self):
    super(SliceTrackerOverviewStep, self).__init__()
    self.caseRootDir = self.getSetting('CasesRootLocation', self.MODULE_NAME)
    self.notifyUserAboutNewData = True

  def cleanup(self):
    self.seriesModel.clear()
    self.trackTargetsButton.setEnabled(False)

  @logmethod(logging.DEBUG)
  def clearData(self):
    self.completeCaseButton.enabled = False
    self.trackTargetsButton.setEnabled(False)
    self.caseWatchBox.reset()
    self.closeCaseButton.enabled = False
    self.updateIntraopSeriesSelectorTable()
    # self.session.close(save=False)
    # slicer.mrmlScene.Clear(0)
    # self.updateIntraopSeriesSelectorColor(None)
    # self.removeSliceAnnotations()
    # self.currentTargets = None
    # self.resetViewSettingButtons()
    # self.resetVisualEffects()
    # self.disconnectKeyEventObservers()

    # if self.customStatusProgressBar:
    #   self.customStatusProgressBar.reset()
    #   self.customStatusProgressBar.hide()

  def onLayoutChanged(self):
    logging.info("Layout changed in %s" % self.NAME)

  def setup(self):
    self.setupCaseInformationArea()
    self.trainingWidget = SliceTrackerTrainingStep()

    self.trackTargetsButton = self.createButton("Track targets", toolTip="Track targets", enabled=False)
    self.skipIntraopSeriesButton = self.createButton("Skip", toolTip="Skip the currently selected series",
                                                     enabled=False)
    self.closeCaseButton = self.createButton("Close case", toolTip="Close case without completing it", enabled=False)
    self.completeCaseButton = self.createButton('Case completed', enabled=False)
    self.setupTargetsTable()
    self.setupIntraopSeriesSelector()

    self.createNewCaseButton = self.createButton("New case")
    self.openCaseButton = self.createButton("Open case")

    self.layout().addWidget(self.collapsibleDirectoryConfigurationArea, 0, 0, 1, 2)
    self.layout().addWidget(self.createNewCaseButton, 1, 0)
    self.layout().addWidget(self.openCaseButton, 1, 1)
    self.layout().addWidget(self.trainingWidget, 2, 0, 1, 2)
    self.layout().addWidget(self.targetTable, 3, 0, 1, 2)
    self.layout().addWidget(self.intraopSeriesSelector, 4, 0)
    self.layout().addWidget(self.skipIntraopSeriesButton, 4, 1)
    self.layout().addWidget(self.trackTargetsButton, 5, 0, 1, 2)
    self.layout().addWidget(self.closeCaseButton, 6, 0, 1, 2)
    self.layout().addWidget(self.completeCaseButton, 7, 0, 1, 2)

    self.layout().setRowStretch(6, 1)

  def setupCaseInformationArea(self):
    self.setupCaseWatchBox()
    self.casesRootDirectoryButton = self.createDirectoryButton(text="Choose cases root location",
                                                               caption="Choose cases root location",
                                                               directory=self.getSetting('CasesRootLocation',
                                                                                         self.MODULE_NAME))
    self.collapsibleDirectoryConfigurationArea = ctk.ctkCollapsibleButton()
    self.collapsibleDirectoryConfigurationArea.collapsed = True
    self.collapsibleDirectoryConfigurationArea.text = "Case Directory Settings"
    self.directoryConfigurationLayout = qt.QGridLayout(self.collapsibleDirectoryConfigurationArea)
    self.directoryConfigurationLayout.addWidget(qt.QLabel("Cases Root Directory"), 1, 0, 1, 1)
    self.directoryConfigurationLayout.addWidget(self.casesRootDirectoryButton, 1, 1, 1, 1)
    self.directoryConfigurationLayout.addWidget(self.caseWatchBox, 2, 0, 1, qt.QSizePolicy.ExpandFlag)

  def setupCaseWatchBox(self):
    watchBoxInformation = [WatchBoxAttribute('CurrentCaseDirectory', 'Directory'),
                           WatchBoxAttribute('CurrentPreopDICOMDirectory', 'Preop DICOM Directory: '),
                           WatchBoxAttribute('CurrentIntraopDICOMDirectory', 'Intraop DICOM Directory: '),
                           WatchBoxAttribute('mpReviewDirectory', 'mpReview Directory: ')]
    self.caseWatchBox = BasicInformationWatchBox(watchBoxInformation, title="Current Case")

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

  def setupIntraopSeriesSelector(self):
    self.intraopSeriesSelector = qt.QComboBox()
    self.seriesModel = qt.QStandardItemModel()
    self.intraopSeriesSelector.setModel(self.seriesModel)

  def setupConnections(self):
    super(SliceTrackerOverviewStep, self).setupConnections()
    self.createNewCaseButton.clicked.connect(self.onCreateNewCaseButtonClicked)
    self.casesRootDirectoryButton.directoryChanged.connect(lambda: setattr(self, "caseRootDir",
                                                                           self.casesRootDirectoryButton.directory))
    self.openCaseButton.clicked.connect(self.onOpenCaseButtonClicked)
    self.closeCaseButton.clicked.connect(self.session.close)
    # self.skipIntraopSeriesButton.clicked.connect(self.onSkipIntraopSeriesButtonClicked)
    self.trackTargetsButton.clicked.connect(self.onTrackTargetsButtonClicked)
    # self.completeCaseButton.clicked.connect(self.onCompleteCaseButtonClicked)
    self.intraopSeriesSelector.connect('currentIndexChanged(QString)', self.onIntraopSeriesSelectionChanged)
    # self.targetTable.connect('clicked(QModelIndex)', self.onTargetTableSelectionChanged)

  def onTrackTargetsButtonClicked(self):
    # self.removeSliceAnnotations()
    # self.targetTableModel.computeCursorDistances = False
    volume = self.logic.getOrCreateVolumeForSeries(self.intraopSeriesSelector.currentText)
    if volume:
      if not self.session.zFrameRegistrationSuccessful and \
          self.getSetting("COVER_TEMPLATE") in self.intraopSeriesSelector.currentText:
        logging.info("Opening ZFrameRegistrationStep")
        # self.openZFrameRegistrationStep(volume)
        return
      # else:
      #   if self.currentResult is None or \
      #      self.session.data.getMostRecentApprovedCoverProstateRegistration() is None or \
      #      self.logic.retryMode or self.getSetting("COVER_PROSTATE") in self.intraopSeriesSelector.currentText:
      #     self.openSegmentationStep(volume)
      #   else:
      #     self.repeatRegistrationForCurrentSelection(volume)

  def onIntraopSeriesSelectionChanged(self, selectedSeries=None):
    # if not self.active:
    # self.removeSliceAnnotations()
    trackingPossible = False
    if selectedSeries:
      trackingPossible = self.logic.isTrackingPossible(selectedSeries)
      logging.info(trackingPossible)
    #   self.showTemplatePathButton.checked = trackingPossible and self.getSetting("COVER_PROSTATE") in selectedSeries
    #   self.setIntraopSeriesButtons(trackingPossible, selectedSeries)
    #   self.configureViewersForSelectedIntraopSeries(selectedSeries)
    #   self.updateSliceAnnotations(selectedSeries)
    # self.updateIntraopSeriesSelectorColor(selectedSeries)
    # self.updateLayoutButtons(trackingPossible, selectedSeries)

  def setupSessionObservers(self):
    super(SliceTrackerOverviewStep, self).setupSessionObservers()
    self.session.addEventObserver(self.session.IncomingPreopDataReceiveFinishedEvent, self.onPreopReceptionFinished)

  def removeSessionEventObservers(self):
    SliceTrackerStep.removeSessionEventObservers(self)
    self.session.removeEventObserver(self.session.IncomingPreopDataReceiveFinishedEvent, self.onPreopReceptionFinished)

  def onCreateNewCaseButtonClicked(self):
    if not self.checkAndWarnUserIfCaseInProgress():
      return
    self.caseDialog = NewCaseSelectionNameWidget(self.caseRootDir)
    selectedButton = self.caseDialog.exec_()
    if selectedButton == qt.QMessageBox.Ok:
      self.session.createNewCase(self.caseDialog.newCaseDirectory)
      self.updateCaseWatchBox()
      self.closeCaseButton.enabled = True

  @logmethod(logging.INFO)
  def onCaseClosed(self, caller, event):
    self.clearData()

  def updateCaseWatchBox(self):
    self.caseWatchBox.setInformation("CurrentCaseDirectory", os.path.relpath(self.session.directory, self.caseRootDir),
                                     toolTip=self.session.directory)
    self.caseWatchBox.setInformation("CurrentPreopDICOMDirectory", os.path.relpath(self.session.preopDICOMDirectory,
                                                                                   self.caseRootDir),
                                     toolTip=self.session.preopDICOMDirectory)
    self.caseWatchBox.setInformation("CurrentIntraopDICOMDirectory", os.path.relpath(self.session.intraopDICOMDirectory,
                                                                                     self.caseRootDir),
                                     toolTip=self.session.intraopDICOMDirectory)
    self.caseWatchBox.setInformation("mpReviewDirectory", os.path.relpath(self.session.preprocessedDirectory,
                                                                          self.caseRootDir),
                                     toolTip=self.session.preprocessedDirectory)

  def checkAndWarnUserIfCaseInProgress(self):
    if self.session.isRunning():
      if not slicer.util.confirmYesNoDisplay("Current case will be closed. Do you want to proceed?"):
        return False
    return True

  @logmethod(logging.INFO)
  def onPreopReceptionFinished(self, caller=None, event=None):
    if self.invokePreProcessing():
      self.startMpReview()
    else:
      slicer.util.infoDisplay("No DICOM data could be processed. Please select another directory.",
                              windowTitle="SliceTracker")

  def startMpReview(self):
    self.setSetting('InputLocation', None, moduleName="mpReview")
    self.layoutManager.selectModule("mpReview")
    mpReview = slicer.modules.mpReviewWidget
    self.setSetting('InputLocation', self.session.preprocessedDirectory, moduleName="mpReview")
    mpReview.onReload()
    slicer.modules.mpReviewWidget.saveButton.clicked.connect(self.onReturnFromMpReview)
    self.layoutManager.selectModule(mpReview.moduleName)

  def onReturnFromMpReview(self):
    slicer.modules.mpReviewWidget.saveButton.clicked.disconnect(self.onReturnFromMpReview)
    self.layoutManager.selectModule(self.MODULE_NAME)
    # slicer.mrmlScene.Clear(0)
    # self.logic.stopSmartDICOMReceiver()  # TODO: this is unclean since there is a time gap
    # TODO!
    # try:
    #   self.preopDataDir = self.logic.getFirstMpReviewPreprocessedStudy(self.session.preprocessedDirectory)
    # except PreProcessedDataError:
    #   self.clearData()
    #   return
    self.simulateIntraopPhaseButton.enabled = self.session.trainingMode
    # self.intraopDataDir = self.intraopDICOMDataDirectory

  def invokePreProcessing(self):
    if not os.path.exists(self.session.preprocessedDirectory):
      self.logic.createDirectory(self.session.preprocessedDirectory)
    from mpReviewPreprocessor import mpReviewPreprocessorLogic
    self.mpReviewPreprocessorLogic = mpReviewPreprocessorLogic()
    progress = self.createProgressDialog()
    progress.canceled.connect(self.mpReviewPreprocessorLogic.cancelProcess)

    @onReturnProcessEvents
    def updateProgressBar(**kwargs):
      for key, value in kwargs.iteritems():
        if hasattr(progress, key):
          setattr(progress, key, value)

    self.mpReviewPreprocessorLogic.importStudy(self.session.preopDICOMDirectory, progressCallback=updateProgressBar)
    success = False
    if self.mpReviewPreprocessorLogic.patientFound():
      success = True
      self.mpReviewPreprocessorLogic.convertData(outputDir=self.session.preprocessedDirectory, copyDICOM=False,
                                                 progressCallback=updateProgressBar)
    progress.canceled.disconnect(self.mpReviewPreprocessorLogic.cancelProcess)
    progress.close()
    return success

  def onOpenCaseButtonClicked(self):
    if not self.checkAndWarnUserIfCaseInProgress():
      return
    self.session.directory = qt.QFileDialog.getExistingDirectory(self.parent().window(), "Select Case Directory", self.caseRootDir) # TODO: move caseRootDir to session
    if not self.session.directory or not self.session.isCaseDirectoryValid():
      slicer.util.warningDisplay("The selected case directory seems not to be valid", windowTitle="SliceTracker")
      self.clearData()
    else:
      self.loadCaseData()

  def loadCaseData(self):
    from mpReview import mpReviewLogic
    savedSessions = self.logic.getSavedSessions(self.currentCaseDirectory)
    if len(savedSessions) > 0: # After registration(s) has been done
      if not self.openSavedSession(savedSessions):
        self.clearData()
    else:
      if os.path.exists(self.mpReviewPreprocessedOutput) and \
              mpReviewLogic.wasmpReviewPreprocessed(self.mpReviewPreprocessedOutput):
        try:
          self.preopDataDir = self.logic.getFirstMpReviewPreprocessedStudy(self.mpReviewPreprocessedOutput)
        except PreProcessedDataError:
          self.clearData()
          return
      else:
        if len(os.listdir(self.session.preopDICOMDirectory)):
          self.startPreProcessingPreopData()
        elif len(os.listdir(self.intraopDICOMDataDirectory)):
          self.logic.usePreopData = False
          self.intraopDataDir = self.intraopDICOMDataDirectory
        else:
          self.startPreopDICOMReceiver()
    self.configureAllTargetDisplayNodes()

  @vtk.calldata_type(vtk.VTK_STRING)
  def onNewImageDataReceived(self, caller, event, callData):
    # self.customStatusProgressBar.text = "New image data has been received."
    self.updateIntraopSeriesSelectorTable()
    # selectedSeries = self.intraopSeriesSelector.currentText

    # if selectedSeries != "" and self.logic.isTrackingPossible(selectedSeries):
    #   self.takeActionOnSelectedSeries(newSeriesNumbers, selectedSeries)

  def takeActionOnSelectedSeries(self, newSeriesNumbers, selectedSeries):
    selectedSeriesNumber = RegistrationResult.getSeriesNumberFromString(selectedSeries)
    if self.getSetting("COVER_TEMPLATE") in selectedSeries and not self.session.zFrameRegistrationSuccessful:
      # TODO: zFrameRegistrationStep
      self.onTrackTargetsButtonClicked()
      return

    if self.active and selectedSeriesNumber in newSeriesNumbers and \
      self.logic.isInGeneralTrackable(self.intraopSeriesSelector.currentText):
      if self.notifyUserAboutNewData and not self.session.data.completed:
        dialog = IncomingDataMessageBox()
        self.notifyUserAboutNewDataAnswer, checked = dialog.exec_()
        self.notifyUserAboutNewData = not checked
      if hasattr(self, "notifyUserAboutNewDataAnswer") and self.notifyUserAboutNewDataAnswer == qt.QMessageBox.AcceptRole:
        self.onTrackTargetsButtonClicked()

  def updateIntraopSeriesSelectorTable(self):
    self.intraopSeriesSelector.blockSignals(True)
    self.seriesModel.clear()
    for series in self.session.seriesList:
      sItem = qt.QStandardItem(series)
      self.seriesModel.appendRow(sItem)
      color = COLOR.YELLOW
      if self.session.data.registrationResultWasApproved(series) or \
        (self.getSetting("COVER_TEMPLATE") in series and
           self.session.zFrameRegistrationSuccessful):
        color = COLOR.GREEN
      elif self.session.data.registrationResultWasSkipped(series):
        color = COLOR.RED
      elif self.session.data.registrationResultWasRejected(series):
        color = COLOR.GRAY
      self.seriesModel.setData(sItem.index(), color, qt.Qt.BackgroundRole)
    self.intraopSeriesSelector.setCurrentIndex(-1)
    self.intraopSeriesSelector.blockSignals(False)
    # self.selectMostRecentEligibleSeries()

  # def selectMostRecentEligibleSeries(self):
  #   if not self.active:
  #     self.intraopSeriesSelector.blockSignals(True)
  #   substring = self.getSetting("NEEDLE_IMAGE")
  #   index = -1
  #   if not self.session.data.getMostRecentApprovedCoverProstateRegistration():
  #     substring = self.getSetting("COVER_TEMPLATE") \
  #       if not self.session.zFrameRegistrationSuccessful else self.getSetting("COVER_PROSTATE")
  #   for item in list(reversed(range(len(self.session.seriesList)))):
  #     series = self.seriesModel.item(item).text()
  #     if substring in series:
  #       if index != -1:
  #         if self.session.data.registrationResultWasApprovedOrRejected(series) or \
  #           self.session.data.registrationResultWasSkipped(series):
  #           break
  #       index = self.intraopSeriesSelector.findText(series)
  #       break
  #     elif self.getSetting("VIBE_IMAGE") in series and index == -1:
  #       index = self.intraopSeriesSelector.findText(series)
  #   rowCount = self.intraopSeriesSelector.model().rowCount()
  #   self.intraopSeriesSelector.setCurrentIndex(index if index != -1 else (rowCount-1 if rowCount else -1))
  #   self.intraopSeriesSelector.blockSignals(False)


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