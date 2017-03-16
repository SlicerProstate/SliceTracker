import logging
import os
import vtk
import qt
import ctk

import slicer
from ..helpers import NewCaseSelectionNameWidget
from ..sessionData import RegistrationResult
from base import SliceTrackerStepLogic, SliceTrackerStep
from training import SliceTrackerTrainingStep
from SlicerProstateUtils.constants import COLOR
from SlicerProstateUtils.decorators import logmethod, onReturnProcessEvents
from SlicerProstateUtils.helpers import WatchBoxAttribute, BasicInformationWatchBox, IncomingDataMessageBox


class SliceTrackerOverViewStepLogic(SliceTrackerStepLogic):

  def __init__(self):
    super(SliceTrackerOverViewStepLogic, self).__init__()
    self.scalarVolumePlugin = slicer.modules.dicomPlugins['DICOMScalarVolumePlugin']()

  def cleanup(self):
    pass

  def applyBiasCorrection(self):
    outputVolume = slicer.vtkMRMLScalarVolumeNode()
    outputVolume.SetName('VOLUME-PREOP-N4')
    slicer.mrmlScene.AddNode(outputVolume)
    params = {'inputImageName': self.session.data.initialVolume.GetID(),
              'maskImageName': self.session.data.initialLabel.GetID(),
              'outputImageName': outputVolume.GetID(),
              'numberOfIterations': '500,400,300'}

    slicer.cli.run(slicer.modules.n4itkbiasfieldcorrection, None, params, wait_for_completion=True)
    self.session.data.initialVolume = outputVolume
    self.session.data.biasCorrectionDone = True


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
    # volume = self.logic.getOrCreateVolumeForSeries(self.intraopSeriesSelector.currentText)
    self.session.takeActionForCurrentSeries()
    # if volume:
    #   if not self.session.zFrameRegistrationSuccessful and \
    #       self.getSetting("COVER_TEMPLATE") in self.intraopSeriesSelector.currentText:
    #
    #     logging.info("Opening ZFrameRegistrationStep")
    #     # self.openZFrameRegistrationStep(volume)
    #     return
      # else:
      #   if self.currentResult is None or \
      #      self.session.data.getMostRecentApprovedCoverProstateRegistration() is None or \
      #      self.logic.retryMode or self.getSetting("COVER_PROSTATE") in self.intraopSeriesSelector.currentText:
      #     self.openSegmentationStep(volume)
      #   else:
      #     self.repeatRegistrationForCurrentSelection(volume)

  @logmethod(logging.INFO)
  def onIntraopSeriesSelectionChanged(self, selectedSeries=None):
    # if not self.active:
    # self.removeSliceAnnotations()
    trackingPossible = False

    self.session.currentSeries = selectedSeries
    volume = self.session.currentSeriesVolume

    if selectedSeries:
      print "onIntraopSeriesSelectionChanged called"
      trackingPossible = self.session.isTrackingPossible(selectedSeries)
      logging.info(trackingPossible)
      self.setIntraopSeriesButtons(trackingPossible, selectedSeries)
      # self.configureViewersForSelectedIntraopSeries(selectedSeries)
    #   self.updateSliceAnnotations(selectedSeries)
    self.intraopSeriesSelector.setStyleSheet(self.session.getColorForSelectedSeries())

      # self.updateLayoutButtons(trackingPossible, selectedSeries)

  def configureViewersForSelectedIntraopSeries(self, selectedSeries):
    if self.session.data.registrationResultWasApproved(selectedSeries) or \
            self.session.data.registrationResultWasRejected(selectedSeries):
      if self.getSetting("COVER_PROSTATE") in selectedSeries and not self.session.data.usePreopData:
        self.setupRedSlicePreview(selectedSeries)
      else:
        print "setupSideBySideRegistrationView"
        # self.setupSideBySideRegistrationView()
    else:
      self.setupRedSlicePreview(selectedSeries)

  def setIntraopSeriesButtons(self, trackingPossible, selectedSeries):
    trackingPossible = trackingPossible if not self.session.data.completed else False
    self.trackTargetsButton.setEnabled(trackingPossible)
    self.skipIntraopSeriesButton.setEnabled(trackingPossible and self.session.isEligibleForSkipping(selectedSeries))

  @vtk.calldata_type(vtk.VTK_STRING)
  def onCurrentSeriesChanged(self, caller, event, callData=None):
    logging.info("Current series selection changed invoked from session")
    logging.info("Series with name %s selected" % callData if callData else "")
    if callData:
      model = self.intraopSeriesSelector.model()
      index = next((i for i in range(model.rowCount()) if model.item(i).text() == callData), None)
      self.intraopSeriesSelector.currentIndex = index

  def setupSessionObservers(self):
    super(SliceTrackerOverviewStep, self).setupSessionObservers()
    self.session.addEventObserver(self.session.IncomingPreopDataReceiveFinishedEvent, self.onPreopReceptionFinished)
    self.session.addEventObserver(self.session.FailedPreprocessedEvent, self.onFailedPreProcessing)
    self.session.addEventObserver(self.session.SuccessfullyPreprocessedEvent, self.onSuccessfulPreProcessing)
    # self.session.addEventObserver(self.session.RegistrationStatusChangedEvent, lambda)

  def removeSessionEventObservers(self):
    SliceTrackerStep.removeSessionEventObservers(self)
    self.session.removeEventObserver(self.session.IncomingPreopDataReceiveFinishedEvent, self.onPreopReceptionFinished)
    self.session.removeEventObserver(self.session.FailedPreprocessedEvent, self.onFailedPreProcessing)
    self.session.removeEventObserver(self.session.SuccessfullyPreprocessedEvent, self.onSuccessfulPreProcessing)

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

  def onActivation(self):
    self.updateIntraopSeriesSelectorTable()

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
      self.startPreProcessingModule()
    else:
      slicer.util.infoDisplay("No DICOM data could be processed. Please select another directory.",
                              windowTitle="SliceTracker")

  def startPreProcessingModule(self):
    self.setSetting('InputLocation', None, moduleName="mpReview")
    self.layoutManager.selectModule("mpReview")
    mpReview = slicer.modules.mpReviewWidget
    self.setSetting('InputLocation', self.session.preprocessedDirectory, moduleName="mpReview")
    mpReview.onReload()
    slicer.modules.mpReviewWidget.saveButton.clicked.connect(self.returnFromPreProcessingModule)
    self.layoutManager.selectModule(mpReview.moduleName)

  def returnFromPreProcessingModule(self):
    slicer.modules.mpReviewWidget.saveButton.clicked.disconnect(self.returnFromPreProcessingModule)
    self.layoutManager.selectModule(self.MODULE_NAME)
    slicer.mrmlScene.Clear(0)
    self.simulateIntraopPhaseButton.enabled = self.session.trainingMode
    self.session.loadPreProcessedData()

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
    self.session.directory = qt.QFileDialog.getExistingDirectory(self.parent().window(), "Select Case Directory",
                                                                 self.caseRootDir) # TODO: move caseRootDir to session

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
    currentIndex = self.intraopSeriesSelector.currentIndex
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
    self.intraopSeriesSelector.setCurrentIndex(currentIndex)
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

  @logmethod(logging.INFO)
  def onZFrameRegistrationSuccessful(self, caller, event):
    self.active = True

  @vtk.calldata_type(vtk.VTK_STRING)
  def onFailedPreProcessing(self, caller, event, callData):
    if slicer.util.confirmYesNoDisplay(callData, windowTitle="SliceTracker"):
      self.startPreProcessingModule()
    else:
      self.session.close()

  def onSuccessfulPreProcessing(self, caller, event):
    self.promptUserAndApplyBiasCorrectionIfNeeded()

  def promptUserAndApplyBiasCorrectionIfNeeded(self):
    if not self.session.data.resumed:
      if slicer.util.confirmYesNoDisplay("Was an endorectal coil used for preop image acquisition?",
                                         windowTitle="SliceTracker"):
        progress = self.createProgressDialog(maximum=2, value=1)
        progress.labelText = '\nBias Correction'
        self.logic.applyBiasCorrection()
        progress.setValue(2)
        progress.close()
    # TODO: self.movingVolumeSelector.setCurrentNode(self.logic.preopVolume)