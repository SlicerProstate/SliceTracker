import os, logging
import vtk, ctk, ast
import shutil
from abc import ABCMeta, abstractmethod

import slicer
from sessionData import SessionData, RegistrationResult, RegistrationTypeData
from constants import SliceTrackerConstants

from exceptions import DICOMValueError, PreProcessedDataError, UnknownSeriesError

from SlicerProstateUtils.constants import DICOMTAGS, FileExtension, STYLE
from SlicerProstateUtils.events import SlicerProstateEvents
from SlicerProstateUtils.helpers import IncomingDataWindow, SmartDICOMReceiver
from SlicerProstateUtils.mixins import ModuleLogicMixin, ModuleWidgetMixin

from SlicerProstateUtils.decorators import logmethod, singleton, onReturnProcessEvents, onExceptionReturnNone, onModuleSelected
from SlicerProstateUtils.decorators import onExceptionReturnFalse

from SliceTrackerRegistration import SliceTrackerRegistrationLogic


class SessionBase(ModuleLogicMixin):

  __metaclass__ = ABCMeta

  DirectoryChangedEvent = vtk.vtkCommand.UserEvent + 203

  _directory = None

  @property
  def directory(self):
    return self._directory

  @directory.setter
  def directory(self, value):
    if value:
      if not os.path.exists(value):
        self.createDirectory(value)
    elif not value and self._directory:
      if self.getDirectorySize(self._directory) == 0:
        shutil.rmtree(self.directory)
    self._directory = value
    if self._directory:
      self.processDirectory()
    self.invokeEvent(self.DirectoryChangedEvent, self.directory)

  def __init__(self):
    pass

  @abstractmethod
  def load(self):
    pass

  @abstractmethod
  def processDirectory(self):
    pass

  def save(self):
    pass


@singleton
class SliceTrackerSession(SessionBase):

  IncomingDataSkippedEvent = SlicerProstateEvents.IncomingDataSkippedEvent
  IncomingPreopDataReceiveFinishedEvent = SlicerProstateEvents.IncomingDataReceiveFinishedEvent + 110

  IncomingIntraopDataReceiveFinishedEvent = SlicerProstateEvents.IncomingDataReceiveFinishedEvent + 111
  NewImageSeriesReceivedEvent = SlicerProstateEvents.NewImageDataReceivedEvent

  DICOMReceiverStatusChanged = SlicerProstateEvents.StatusChangedEvent
  DICOMReceiverStoppedEvent = SlicerProstateEvents.DICOMReceiverStoppedEvent

  NewCaseStartedEvent = vtk.vtkCommand.UserEvent + 501
  CloseCaseEvent = vtk.vtkCommand.UserEvent + 502
  CaseOpenedEvent = vtk.vtkCommand.UserEvent + 503

  ZFrameRegistrationSuccessfulEvent = vtk.vtkCommand.UserEvent + 140
  PreprocessingSuccessfulEvent = vtk.vtkCommand.UserEvent + 141
  FailedPreprocessedEvent = vtk.vtkCommand.UserEvent + 142
  LoadingMetadataSuccessfulEvent = vtk.vtkCommand.UserEvent + 143
  SegmentationCancelledEvent = vtk.vtkCommand.UserEvent + 144

  CurrentSeriesChangedEvent = vtk.vtkCommand.UserEvent + 151
  RegistrationStatusChangedEvent = vtk.vtkCommand.UserEvent + 152

  InitiateZFrameCalibrationEvent = vtk.vtkCommand.UserEvent + 160
  InitiateSegmentationEvent = vtk.vtkCommand.UserEvent + 161
  InitiateRegistrationEvent = vtk.vtkCommand.UserEvent + 162
  InitiateEvaluationEvent = vtk.vtkCommand.UserEvent + 163

  CurrentResultChangedEvent = vtk.vtkCommand.UserEvent + 234
  ApprovedEvent = RegistrationResult.ApprovedEvent
  SkippedEvent = RegistrationResult.SkippedEvent
  RejectedEvent = RegistrationResult.RejectedEvent

  ResultEvents = [ApprovedEvent, SkippedEvent, RejectedEvent]

  MODULE_NAME = "SliceTracker"

  @property
  def steps(self):
    return self._steps

  @steps.setter
  def steps(self, value):
    for step in self.steps:
      step.removeSessionEventObservers()
    self._steps = value

  @property
  def preprocessedDirectory(self):
    return os.path.join(self.directory, "mpReviewPreprocessed") if self.directory else None

  @property
  def preopDICOMDirectory(self):
    return os.path.join(self.directory, "DICOM", "Preop") if self.directory else None

  @property
  def intraopDICOMDirectory(self):
    return os.path.join(self.directory, "DICOM", "Intraop") if self.directory else None

  @property
  def outputDirectory(self):
    # was outputDir
    return os.path.join(self.directory, "SliceTrackerOutputs")

  @property
  def approvedCoverTemplate(self):
    return self.data.zFrameVolume

  @approvedCoverTemplate.setter
  def approvedCoverTemplate(self, volume):
    self.data.zFrameVolume = volume
    self.zFrameRegistrationSuccessful = volume is not None

  @property
  def zFrameRegistrationSuccessful(self):
    self._zFrameRegistrationSuccessful = getattr(self, "_zFrameRegistrationSuccessful", None)
    return self.data.zFrameTransform is not None and self._zFrameRegistrationSuccessful

  @zFrameRegistrationSuccessful.setter
  def zFrameRegistrationSuccessful(self, value):
    self._zFrameRegistrationSuccessful = value
    if self._zFrameRegistrationSuccessful:
      self.save()
      self.invokeEvent(self.ZFrameRegistrationSuccessfulEvent)

  @property
  def currentResult(self):
    return self._getCurrentResult()

  @onExceptionReturnNone
  def _getCurrentResult(self):
    return self.data.registrationResults[self._currentResult]

  @currentResult.setter
  def currentResult(self, series):
    if self.currentResult and self.currentResult.name == series:
      return
    if self.currentResult is not None:
      self.currentResult.removeEventObservers()
    self._currentResult = series
    if self.currentResult:
      for event in RegistrationResult.StatusEvents.values():
        self.currentResult.addEventObserver(event, self.onRegistrationResultStatusChanged)
    self.invokeEvent(self.CurrentResultChangedEvent)

  @property
  def currentSeries(self):
    self._currentSeries = getattr(self, "_currentSeries", None)
    return self._currentSeries

  @currentSeries.setter
  def currentSeries(self, series):
    if series == self.currentSeries:
      return
    print "set current Series on session"
    if series and series not in self.seriesList :
      raise UnknownSeriesError("Series %s is unknown" % series)
    self._currentSeries = series
    self.invokeEvent(self.CurrentSeriesChangedEvent, series)

  @property
  def currentSeriesVolume(self):
    if not self.currentSeries:
      return None
    else:
      return self.getOrCreateVolumeForSeries(self.currentSeries)

  @property
  def movingVolume(self):
    self._movingVolume = getattr(self, "_movingVolume", None)
    return self._movingVolume

  @movingVolume.setter
  def movingVolume(self, value):
    self._movingVolume = value

  @property
  def movingLabel(self):
    self._movingLabel = getattr(self, "_movingLabel", None)
    return self._movingLabel

  @movingLabel.setter
  def movingLabel(self, value):
    self._movingLabel = value

  @property
  def movingTargets(self):
    self._movingTargets = getattr(self, "_movingTargets", None)
    if self.isCurrentSeriesCoverProstateInNonPreopMode():
      return self.data.initialTargets
    return self._movingTargets

  @movingTargets.setter
  def movingTargets(self, value):
    if self.isCurrentSeriesCoverProstateInNonPreopMode():
      self.data.initialTargets = value
    self._movingTargets = value
    
  @property
  def fixedVolume(self):
    self._fixedVolume = getattr(self, "_fixedVolume", None)
    if self.isCurrentSeriesCoverProstateInNonPreopMode():
      return self.data.initialVolume
    return self._fixedVolume

  @fixedVolume.setter
  def fixedVolume(self, value):
    if self.isCurrentSeriesCoverProstateInNonPreopMode():
      self.data.initialVolume = value
    self._fixedVolume = value

  @property
  def fixedLabel(self):
    self._fixedLabel = getattr(self, "_fixedLabel", None)
    if self.isCurrentSeriesCoverProstateInNonPreopMode():
      return self.data.initialLabel
    return self._fixedLabel

  @fixedLabel.setter
  def fixedLabel(self, value):
    if self.isCurrentSeriesCoverProstateInNonPreopMode():
      self.data.initialLabel = value
    self._fixedLabel = value

  def __init__(self):
    SessionBase.__init__(self)
    self.registrationLogic = SliceTrackerRegistrationLogic()
    self._steps = []
    self.resetAndInitializeMembers()
    self.addMrmlSceneClearObserver()

  def resetAndInitializeMembers(self):
    self.initializeColorNodes()
    self.directory = None
    self.data = SessionData()
    self.data.addEventObserver(self.data.NewResultCreatedEvent, self.onNewRegistrationResultCreated)
    self.trainingMode = False
    self.resetPreopDICOMReceiver()
    self.resetIntraopDICOMReceiver()
    self.loadableList = {}
    self.seriesList = []
    self.alreadyLoadedSeries = {}
    self._currentResult = None
    self._currentSeries = None
    self.retryMode = False
    self.lastSelectedModelIndex = None
    self.previousStep = None

  def initializeColorNodes(self):
    from mpReview import mpReviewLogic
    self.mpReviewColorNode, self.structureNames = mpReviewLogic.loadColorTable(self.getSetting("Color_File_Name"))
    self.segmentedColorName = self.getSetting("Segmentation_Color_Name")
    self.segmentedLabelValue = self.mpReviewColorNode.GetColorIndexByName(self.segmentedColorName)

  def __del__(self):
    self.clearData()
    if self.mrmlSceneObserver:
      self.mrmlSceneObserver = slicer.mrmlScene.RemoveObserver(self.mrmlSceneObserver)

  def addMrmlSceneClearObserver(self):

    @onModuleSelected(self.MODULE_NAME)
    def onMrmlSceneCleared(caller, event):
      logging.debug("called onMrmlSceneCleared in %s" % self.__class__.__name__)
      self.initializeColorNodes()

    self.mrmlSceneObserver = slicer.mrmlScene.AddObserver(slicer.mrmlScene.EndCloseEvent, onMrmlSceneCleared)

  @onExceptionReturnFalse
  def isCurrentSeriesCoverProstateInNonPreopMode(self):
    return self.getSetting("COVER_PROSTATE") in self.currentSeries and not self.data.usePreopData

  def isPreProcessing(self):
    return slicer.util.selectedModule() != self.MODULE_NAME

  def isCaseDirectoryValid(self):
    return os.path.exists(self.preopDICOMDirectory) and os.path.exists(self.intraopDICOMDirectory)

  def getSetting(self, setting, moduleName=None, default=None):
    return SessionBase.getSetting(self, setting, moduleName=self.MODULE_NAME, default=default)

  def setSetting(self, setting, value, moduleName=None):
    return SessionBase.setSetting(self, setting, value, moduleName=self.MODULE_NAME)

  def registerStep(self, step):
    logging.debug("Registering step %s" % step.NAME)
    if step not in self.steps:
      self.steps.append(step)

  def getStep(self, stepName):
    return next((x for x in self.steps if x.NAME == stepName), None)

  def isRunning(self):
    return not self.directory in [None, '']

  def clearData(self):
    self.resetAndInitializeMembers()

  def processDirectory(self):
    self.newCaseCreated = getattr(self, "newCaseCreated", False)
    if self.newCaseCreated:
      return
    if not self.directory or not self.isCaseDirectoryValid():
      slicer.util.warningDisplay("The selected case directory seems not to be valid", windowTitle="SliceTracker")
      self.close(save=False)
    else:
      self.loadCaseData()
      self.invokeEvent(self.CaseOpenedEvent)

  def createNewCase(self, destination):
    # TODO: self.continueOldCase = False
    self.newCaseCreated = True
    self.resetAndInitializeMembers()
    self.directory = destination
    self.createDirectory(self.preopDICOMDirectory)
    self.createDirectory(self.intraopDICOMDirectory)
    self.createDirectory(self.preprocessedDirectory)
    self.createDirectory(self.outputDirectory)
    self.startPreopDICOMReceiver()
    self.newCaseCreated = False
    self.invokeEvent(self.NewCaseStartedEvent)

  def close(self, save=False):
    if not self.isRunning():
      return
    message = None
    if save:
      success, failedFileNames = self.data.close(self.outputDirectory)
      message = "Case data has been save successfully." if success else \
        "The following data failed to saved:\n %s" % failedFileNames
    self.resetAndInitializeMembers()
    self.invokeEvent(self.CloseCaseEvent, str(message))

  def save(self):
    success, failedFileNames = self.data.save(self.outputDirectory)
    return success and not len(failedFileNames), "The following data failed to saved:\n %s" % failedFileNames

  def complete(self):
    self.data.completed = True
    self.close(save=True)

  def load(self):
    self._loading = True
    slicer.app.layoutManager().blockSignals(True)
    filename = os.path.join(self.outputDirectory, SliceTrackerConstants.JSON_FILENAME)
    if not os.path.exists(filename):
      return
    self.data.load(filename)
    coverProstate = self.data.getMostRecentApprovedCoverProstateRegistration()
    if coverProstate:
      if not self.data.initialVolume:
        self.data.initialVolume = coverProstate.volumes.moving if self.data.usePreopData else coverProstate.volumes.fixed
      self.data.initialTargets = coverProstate.targets.original
      if self.data.usePreopData:  # TODO: makes sense?
        self.data.preopLabel = coverProstate.labels.moving
    if self.data.zFrameTransform:
      self._zFrameRegistrationSuccessful = True
    self._loading = False
    slicer.app.layoutManager().blockSignals(False)
    self.invokeEvent(self.LoadingMetadataSuccessfulEvent)

  def startPreopDICOMReceiver(self):
    self.resetPreopDICOMReceiver()
    self.preopDICOMReceiver = IncomingDataWindow(incomingDataDirectory=self.preopDICOMDirectory,
                                                 skipText="No preoperative images available")
    self.preopDICOMReceiver.addEventObserver(SlicerProstateEvents.IncomingDataSkippedEvent,
                                             self.onSkippingPreopDataReception)
    self.preopDICOMReceiver.addEventObserver(SlicerProstateEvents.IncomingDataCanceledEvent,
                                             lambda caller, event: self.close())
    self.preopDICOMReceiver.addEventObserver(SlicerProstateEvents.IncomingDataReceiveFinishedEvent,
                                             self.onPreopDataReceptionFinished)
    self.preopDICOMReceiver.show()

  def onSkippingPreopDataReception(self, caller, event):
    self.data.usePreopData = False
    self.startIntraopDICOMReceiver()
    self.invokeEvent(self.IncomingDataSkippedEvent)

  def onPreopDataReceptionFinished(self, caller, event):
    self.data.usePreopData = True
    self.startIntraopDICOMReceiver()
    self.invokeEvent(self.IncomingPreopDataReceiveFinishedEvent)

  def resetPreopDICOMReceiver(self):
    self.preopDICOMReceiver = getattr(self, "preopDICOMReceiver", None)
    if self.preopDICOMReceiver:
      self.preopDICOMReceiver.hide()
      self.preopDICOMReceiver.removeEventObservers()
      self.preopDICOMReceiver = None

  def startIntraopDICOMReceiver(self):
    self.resetPreopDICOMReceiver()
    logging.info("Starting DICOM Receiver for intra-procedural data")
    if not self.data.completed:
      self.resetIntraopDICOMReceiver()
      self.intraopDICOMReceiver = SmartDICOMReceiver(self.intraopDICOMDirectory)
      self._observeIntraopDICOMReceiverEvents()
      self.intraopDICOMReceiver.start(not (self.trainingMode or self.data.completed))
    else:
      self.invokeEvent(SlicerProstateEvents.DICOMReceiverStoppedEvent)
    self.importDICOMSeries(self.getFileList(self.intraopDICOMDirectory))
    if self.intraopDICOMReceiver:
      self.intraopDICOMReceiver.forceStatusChangeEvent()

  def resetIntraopDICOMReceiver(self):
    self.intraopDICOMReceiver = getattr(self, "intraopDICOMReceiver", None)
    if self.intraopDICOMReceiver:
      self.intraopDICOMReceiver.stop()
      self.intraopDICOMReceiver.removeEventObservers()

  def _observeIntraopDICOMReceiverEvents(self):
    self.intraopDICOMReceiver.addEventObserver(self.intraopDICOMReceiver.IncomingDataReceiveFinishedEvent,
                                               self.onDICOMSeriesReceived)
    # self.intraopDICOMReceiver.addEventObserver(SlicerProstateEvents.StatusChangedEvent,
    #                                            self.onDICOMReceiverStatusChanged)
    # self.intraopDICOMReceiver.addEventObserver(SlicerProstateEvents.DICOMReceiverStoppedEvent,
    #                                            self.onSmartDICOMReceiverStopped)

    # self.logic.addEventObserver(SlicerProstateEvents.StatusChangedEvent, self.onDICOMReceiverStatusChanged)
    # self.logic.addEventObserver(SlicerProstateEvents.DICOMReceiverStoppedEvent, self.onIntraopDICOMReceiverStopped)


  @vtk.calldata_type(vtk.VTK_STRING)
  def onDICOMSeriesReceived(self, caller, event, callData):
    self.importDICOMSeries(ast.literal_eval(callData))
    if self.trainingMode is True:
      self.resetIntraopDICOMReceiver()

  def importDICOMSeries(self, newFileList):
    indexer = ctk.ctkDICOMIndexer()

    newSeries = []
    for currentIndex, currentFile in enumerate(newFileList, start=1):
      self.invokeEvent(SlicerProstateEvents.NewFileIndexedEvent,
                       ["Indexing file %s" % currentFile, len(newFileList), currentIndex].__str__())
      slicer.app.processEvents()
      currentFile = os.path.join(self.intraopDICOMDirectory, currentFile)
      indexer.addFile(slicer.dicomDatabase, currentFile, None)
      series = self.makeSeriesNumberDescription(currentFile)
      if series not in self.seriesList:
        self.seriesList.append(series)
        newSeries.append(series)
        self.loadableList[series] = self.createLoadableFileListForSeries(series)
    self.seriesList = sorted(self.seriesList, key=lambda s: RegistrationResult.getSeriesNumberFromString(s))

    if len(newFileList):
      if self.data.usePreopData:
        self.verifyPatientIDEquality(newFileList)
      self.invokeEvent(self.NewImageSeriesReceivedEvent, newSeries.__str__())
      # self.invokeEventForMostRecentEligibleSeries()

  def verifyPatientIDEquality(self, receivedFiles):
    seriesNumberPatientID = self.getAdditionalInformationForReceivedSeries(receivedFiles)
    dicomFileName = self.getFileList(self.preopDICOMDirectory)[0]
    currentInfo = self.getPatientInformation(os.path.join(self.preopDICOMDirectory, dicomFileName))
    currentID = currentInfo["PatientID"]
    patientName = currentInfo["PatientName"]
    for seriesNumber, receivedInfo in seriesNumberPatientID.iteritems():
      patientID = receivedInfo["PatientID"]
      if patientID is not None and patientID != currentID:
        message = 'WARNING:\n' \
                  'Current case:\n' \
                  '  Patient ID: {0}\n' \
                  '  Patient Name: {1}\n' \
                  'Received image\n' \
                  '  Patient ID: {2}\n' \
                  '  Patient Name : {3}\n\n' \
                  'Do you want to keep this series? '.format(currentID, patientName,
                                                             patientID, receivedInfo["PatientName"])
        if not slicer.util.confirmYesNoDisplay(message, title="Patient IDs Not Matching", windowTitle="SliceTracker"):
          self.deleteSeriesFromSeriesList(seriesNumber)

  def getOrCreateVolumeForSeries(self, series):
    try:
      volume = self.alreadyLoadedSeries[series]
    except KeyError:
      logging.info("Need to load volume")
      files = self.loadableList[series]
      loadables = self.scalarVolumePlugin.examine([files])
      success, volume = slicer.util.loadVolume(files[0], returnNode=True)
      volume.SetName(loadables[0].name)
      self.alreadyLoadedSeries[series] = volume
    slicer.app.processEvents()
    return volume

  def createLoadableFileListForSeries(self, series):
    seriesNumber = RegistrationResult.getSeriesNumberFromString(series)
    loadableList = []
    for dcm in self.getFileList(self.intraopDICOMDirectory):
      currentFile = os.path.join(self.intraopDICOMDirectory, dcm)
      currentSeriesNumber = int(self.getDICOMValue(currentFile, DICOMTAGS.SERIES_NUMBER))
      if currentSeriesNumber and currentSeriesNumber == seriesNumber:
        loadableList.append(currentFile)
    return loadableList

  def deleteSeriesFromSeriesList(self, seriesNumber):
    for series in self.seriesList:
      currentSeriesNumber = RegistrationResult.getSeriesNumberFromString(series)
      if currentSeriesNumber == seriesNumber:
        self.seriesList.remove(series)
        for seriesFile in self.loadableList[series]:
          logging.debug("removing {} from filesystem".format(seriesFile))
          os.remove(seriesFile)
        del self.loadableList[series]

  def makeSeriesNumberDescription(self, dcmFile):
    seriesDescription = self.getDICOMValue(dcmFile, DICOMTAGS.SERIES_DESCRIPTION)
    seriesNumber = self.getDICOMValue(dcmFile, DICOMTAGS.SERIES_NUMBER)
    if not (seriesNumber and seriesDescription):
      raise DICOMValueError("Missing Attribute(s):\nFile: {}\nseriesNumber: {}\nseriesDescription: {}"
                            .format(dcmFile, seriesNumber, seriesDescription))
    return "{}: {}".format(seriesNumber, seriesDescription)

  def getAdditionalInformationForReceivedSeries(self, fileList):
    seriesNumberPatientID = {}
    for currentFile in [os.path.join(self.intraopDICOMDirectory, f) for f in fileList]:
      seriesNumber = int(self.getDICOMValue(currentFile, DICOMTAGS.SERIES_NUMBER))
      if seriesNumber not in seriesNumberPatientID.keys():
        seriesNumberPatientID[seriesNumber]= self.getPatientInformation(currentFile)
    return seriesNumberPatientID

  def getPatientInformation(self, currentFile):
    return {
      "PatientID": self.getDICOMValue(currentFile, DICOMTAGS.PATIENT_ID),
      "PatientName": self.getDICOMValue(currentFile, DICOMTAGS.PATIENT_NAME),
      "SeriesDescription": self.getDICOMValue(currentFile, DICOMTAGS.SERIES_DESCRIPTION)}

  def getSeriesForSubstring(self, substring):
    for series in reversed(self.seriesList):
      if substring in series:
        return series
    return None

  def loadPreProcessedData(self):
    try:
      self.loadPreopData(self.getFirstMpReviewPreprocessedStudy(self.preprocessedDirectory))
      self.startIntraopDICOMReceiver()
    except PreProcessedDataError:
      self.close(save=False)

  def loadCaseData(self):
    if not os.path.exists(os.path.join(self.outputDirectory, SliceTrackerConstants.JSON_FILENAME)):
      from mpReview import mpReviewLogic
      if mpReviewLogic.wasmpReviewPreprocessed(self.preprocessedDirectory):
        self.loadPreProcessedData()
      else:
        if len(os.listdir(self.preopDICOMDirectory)):
          self.startPreopDICOMReceiver()
        elif len(os.listdir(self.intraopDICOMDirectory)):
          self.data.usePreopData = False
          self.startIntraopDICOMReceiver()
        else:
          self.startPreopDICOMReceiver()
    else:
      self.openSavedSession()

  def openSavedSession(self):
    self.load()
    if slicer.util.confirmYesNoDisplay("A %s session has been found for the selected case. Do you want to %s?" \
              % ("completed" if self.data.completed else "started",
                 "open it" if self.data.completed else "continue this session")):
      self.data.resumed = not self.data.completed
      if self.data.usePreopData:
        self.loadPreProcessedData()
      else:
        if self.data.initialTargets:
          self.setupPreopLoadedTargets()
        self.startIntraopDICOMReceiver()
    else:
      self.clearData()

  def setupPreopLoadedTargets(self):
    targets = self.data.initialTargets
    ModuleWidgetMixin.setFiducialNodeVisibility(targets, show=True)
    self.applyDefaultTargetDisplayNode(targets)
    self.markupsLogic.JumpSlicesToNthPointInMarkup(targets.GetID(), 0)
    # self.targetTable.selectRow(0)
    # self.updateDisplacementChartTargetSelectorTable()

  def applyDefaultTargetDisplayNode(self, targetNode, new=False):
    displayNode = None if new else targetNode.GetDisplayNode()
    modifiedDisplayNode = self.setupDisplayNode(displayNode, True)
    targetNode.SetAndObserveDisplayNodeID(modifiedDisplayNode.GetID())

  def setupDisplayNode(self, displayNode=None, starBurst=False):
    if not displayNode:
      displayNode = slicer.vtkMRMLMarkupsDisplayNode()
      slicer.mrmlScene.AddNode(displayNode)
    displayNode.SetTextScale(0)
    displayNode.SetGlyphScale(2.5)
    if starBurst:
      displayNode.SetGlyphType(slicer.vtkMRMLAnnotationPointDisplayNode.StarBurst2D)
    return displayNode

  def getFirstMpReviewPreprocessedStudy(self, directory):
    # TODO add check here and selected the one which has targets in it
    # TODO: if several studies are available provide a drop down or anything similar for choosing
    directoryNames = [x[0] for x in os.walk(directory)]
    assert len(directoryNames) > 1
    return directoryNames[1]

  def loadPreopData(self, directory):
    message = self.loadMpReviewProcessedData(directory)
    logging.info(message)
    if message or not self.loadT2Label() or not self.loadPreopVolume() or not self.loadPreopTargets():
      self.invokeEvent(self.FailedPreprocessedEvent,
                       "Loading preop data failed.\nMake sure that the correct mpReview directory structure is used."
                       "\n\nSliceTracker expects a T2 volume, WholeGland segmentation and target(s). Do you want to "
                       "open/revisit pre-processing for the current case?")
    else:
      self.data.usePreopData = True
      self.setupPreopLoadedTargets()
      self.invokeEvent(self.PreprocessingSuccessfulEvent)
      # self.logic.preopLabel.GetDisplayNode().SetAndObserveColorNodeID(self.mpReviewColorNode.GetID())

  def loadMpReviewProcessedData(self, directory):
    from mpReview import mpReviewLogic
    resourcesDir = os.path.join(directory, 'RESOURCES')
    logging.debug(resourcesDir)
    if not os.path.exists(resourcesDir):
      message = "The selected directory does not fit the mpReview directory structure. Make sure that you select the " \
                "study root directory which includes directories RESOURCES"
      return message

    # self.progress = self.createProgressDialog(maximum=len(os.listdir(resourcesDir)))
    # seriesMap, metaFile = mpReviewLogic.loadMpReviewProcessedData(resourcesDir,
    #                                                               updateProgressCallback=self.updateProgressBar)
    seriesMap, metaFile = mpReviewLogic.loadMpReviewProcessedData(resourcesDir)
    # self.progress.delete()

    self.data.initialTargetsPath = os.path.join(directory, 'Targets')

    self.loadPreopImageAndLabel(seriesMap)

    if self.preopSegmentationPath is None:
      message = "No segmentations found.\nMake sure that you used mpReview for segmenting the prostate first and using " \
                "its output as the preop data input here."
      return message
    return None

  def loadPreopImageAndLabel(self, seriesMap):
    self.preopImagePath = None
    self.preopSegmentationPath = None
    segmentedColorName = self.getSetting("Segmentation_Color_Name")

    for series in seriesMap:
      seriesName = str(seriesMap[series]['LongName'])
      logging.debug('series Number ' + series + ' ' + seriesName)

      imagePath = os.path.join(seriesMap[series]['NRRDLocation'])
      segmentationPath = os.path.dirname(os.path.dirname(imagePath))
      segmentationPath = os.path.join(segmentationPath, 'Segmentations')

      if not os.path.exists(segmentationPath):
        continue
      else:
        if any(segmentedColorName in name for name in os.listdir(segmentationPath)):
          logging.debug(' FOUND THE SERIES OF INTEREST, ITS ' + seriesName)
          logging.debug(' LOCATION OF VOLUME : ' + str(seriesMap[series]['NRRDLocation']))
          logging.debug(' LOCATION OF IMAGE path : ' + str(imagePath))

          logging.debug(' LOCATION OF SEGMENTATION path : ' + segmentationPath)

          self.preopImagePath = seriesMap[series]['NRRDLocation']
          self.preopSegmentationPath = segmentationPath
          break

  def loadT2Label(self):
    if self.data.initialLabel:
      return True
    mostRecentFilename = self.getMostRecentWholeGlandSegmentation(self.preopSegmentationPath)
    success = False
    if mostRecentFilename:
      filename = os.path.join(self.preopSegmentationPath, mostRecentFilename)
      success, self.data.initialLabel = slicer.util.loadLabelVolume(filename, returnNode=True)
      if success:
        self.data.initialLabel.SetName('t2-label')
    return success

  def loadPreopVolume(self):
    if self.data.initialVolume:
      return True
    success, self.data.initialVolume = slicer.util.loadVolume(self.preopImagePath, returnNode=True)
    if success:
      self.data.initialVolume.SetName('VOLUME-PREOP')
    return success

  def loadPreopTargets(self):
    if self.data.initialTargets:
      return True
    if not os.path.exists(self.data.initialTargetsPath):
      return False
    mostRecentTargets = self.getMostRecentTargetsFile(self.data.initialTargetsPath)
    success = False
    if mostRecentTargets:
      filename = os.path.join(self.data.initialTargetsPath, mostRecentTargets)
      success, self.data.initialTargets = slicer.util.loadMarkupsFiducialList(filename, returnNode=True)
      if success:
        self.data.initialTargets.SetName('targets-PREOP')
        self.data.initialTargets.SetLocked(True)
    return success

  def getMostRecentWholeGlandSegmentation(self, path):
    return self.getMostRecentFile(path, FileExtension.NRRD, filter="WholeGland")

  def getMostRecentTargetsFile(self, path):
    return self.getMostRecentFile(path, FileExtension.FCSV)

  def getColorForSelectedSeries(self, series=None):
    series = series if series else self.currentSeries
    if series in [None, '']:
      return STYLE.WHITE_BACKGROUND
    style = STYLE.YELLOW_BACKGROUND
    if not self.isTrackingPossible(series):
      if self.data.registrationResultWasApproved(series) or \
              (self.zFrameRegistrationSuccessful and self.getSetting("COVER_TEMPLATE") in series):
        style = STYLE.GREEN_BACKGROUND
      elif self.data.registrationResultWasSkipped(series):
        style = STYLE.RED_BACKGROUND
      elif self.data.registrationResultWasRejected(series):
        style = STYLE.GRAY_BACKGROUND
    return style

  def isTrackingPossible(self, series):
    if self.data.completed:
      logging.debug("No tracking possible. Case has been marked as completed!")
      return False
    if self.isInGeneralTrackable(series) and self.resultHasNotBeenProcessed(series):
      if self.getSetting("NEEDLE_IMAGE") in series:
        return self.data.getMostRecentApprovedCoverProstateRegistration()
      elif self.getSetting("COVER_PROSTATE") in series:
        return self.zFrameRegistrationSuccessful
      elif self.isCoverTemplateTrackable(series):
        return True
    return False

  def isCoverTemplateTrackable(self, series):
    if not self.getSetting("COVER_TEMPLATE") in series:
      return False
    if not self.approvedCoverTemplate:
      return True
    currentSeriesNumber = RegistrationResult.getSeriesNumberFromString(series)
    vName = self.approvedCoverTemplate.GetName()
    approvedSeriesNumber = int(vName.split(":" if vName.find(":") > -1 else "-")[0])
    return currentSeriesNumber > approvedSeriesNumber

  def isInGeneralTrackable(self, series):
    return self.isAnyListItemInString(series, [self.getSetting("COVER_TEMPLATE"), self.getSetting("COVER_PROSTATE"),
                                               self.getSetting("NEEDLE_IMAGE")])

  def resultHasNotBeenProcessed(self, series):
    return not (self.data.registrationResultWasApproved(series) or
                self.data.registrationResultWasSkipped(series) or
                self.data.registrationResultWasRejected(series))

  def isEligibleForSkipping(self, series):
    return not self.isAnyListItemInString(series,[self.getSetting("COVER_PROSTATE"), self.getSetting("COVER_TEMPLATE")])

  def takeActionForCurrentSeries(self):
    event = None
    callData = None
    if self.getSetting("COVER_PROSTATE") in self.currentSeries:
      event = self.InitiateSegmentationEvent
      callData = str(False)
    elif self.getSetting("COVER_TEMPLATE") in self.currentSeries:
      event = self.InitiateZFrameCalibrationEvent
    elif self.getSetting("NEEDLE_IMAGE") in self.currentSeries:
      self.onInvokeRegistration(initial=False)
      return
    if event:
      self.invokeEvent(event, callData)
    else:
      raise UnknownSeriesError("Action for currently selected series unknown")

  def retryRegistration(self):
    self.invokeEvent(self.InitiateSegmentationEvent, str(True))

  def getRegistrationResultNameAndGeneratedSuffix(self, name):
    nOccurrences = sum([1 for result in self.data.getResultsAsList() if name in result.name])
    suffix = ""
    if nOccurrences:
      suffix = "_Retry_" + str(nOccurrences)
    return name, suffix

  def onInvokeRegistration(self, initial=True, retryMode=False):
    self.progress = slicer.util.createProgressDialog(maximum=4, value=1)
    if initial:
      self.applyInitialRegistration(retryMode, progressCallback=self.updateProgressBar)
    else:
      self.applyRegistration(progressCallback=self.updateProgressBar)
    self.progress.close()
    self.progress = None
    logging.debug('Re-Registration is done')

  @onReturnProcessEvents
  def updateProgressBar(self, **kwargs):
    if self.progress:
      for key, value in kwargs.iteritems():
        if hasattr(self.progress, key):
          setattr(self.progress, key, value)

  def generateNameAndCreateRegistrationResult(self, fixedVolume):
    name, suffix = self.getRegistrationResultNameAndGeneratedSuffix(fixedVolume.GetName())
    result = self.data.createResult(name + suffix)
    result.suffix = suffix
    self.registrationLogic.registrationResult = result
    return result

  def applyInitialRegistration(self, retryMode, progressCallback=None):
    if not retryMode:
      self.data.initializeRegistrationResults()

    self.runBRAINSResample(inputVolume=self.fixedLabel, referenceVolume=self.fixedVolume,
                           outputVolume=self.fixedLabel)
    self._runRegistration(self.fixedVolume, self.fixedLabel, self.movingVolume,
                          self.movingLabel, self.movingTargets, progressCallback)

  def applyRegistration(self, progressCallback=None):

    coverProstateRegResult = self.data.getMostRecentApprovedCoverProstateRegistration()
    lastRigidTfm = self.data.getLastApprovedRigidTransformation()
    lastApprovedTfm = self.data.getMostRecentApprovedTransform()
    initialTransform = lastApprovedTfm if lastApprovedTfm else lastRigidTfm


    fixedLabel = self.volumesLogic.CreateAndAddLabelVolume(slicer.mrmlScene, self.currentSeriesVolume,
                                                           self.currentSeriesVolume.GetName() + '-label')

    self.runBRAINSResample(inputVolume=coverProstateRegResult.labels.fixed, referenceVolume=self.currentSeriesVolume,
                           outputVolume=fixedLabel, warpTransform=initialTransform)

    self.dilateMask(fixedLabel, dilateValue=self.segmentedLabelValue)
    self._runRegistration(self.currentSeriesVolume, fixedLabel, coverProstateRegResult.volumes.fixed,
                         coverProstateRegResult.labels.fixed, coverProstateRegResult.targets.approved, progressCallback)

  def _runRegistration(self, fixedVolume, fixedLabel, movingVolume, movingLabel, targets, progressCallback):
    result = self.generateNameAndCreateRegistrationResult(fixedVolume)
    parameterNode = slicer.vtkMRMLScriptedModuleNode()
    parameterNode.SetAttribute('FixedImageNodeID', fixedVolume.GetID())
    parameterNode.SetAttribute('FixedLabelNodeID', fixedLabel.GetID())
    parameterNode.SetAttribute('MovingImageNodeID', movingVolume.GetID())
    parameterNode.SetAttribute('MovingLabelNodeID', movingLabel.GetID())
    parameterNode.SetAttribute('TargetsNodeID', targets.GetID())
    self.registrationLogic.run(parameterNode, progressCallback=progressCallback)
    self.addTargetsToMrmlScene(result)
    self.invokeEvent(self.InitiateEvaluationEvent)

  def addTargetsToMrmlScene(self, result):
    targetNodes = result.targets.asDict()
    for regType in RegistrationTypeData.RegistrationTypes:
      if targetNodes[regType]:
        slicer.mrmlScene.AddNode(targetNodes[regType])

  def runBRAINSResample(self, inputVolume, referenceVolume, outputVolume, warpTransform=None):

    params = {'inputVolume': inputVolume, 'referenceVolume': referenceVolume, 'outputVolume': outputVolume,
              'interpolationMode': 'NearestNeighbor', 'pixelType':'short'}
    if warpTransform:
      params['warpTransform'] = warpTransform

    logging.debug('About to run BRAINSResample CLI with those params: %s' % params)
    slicer.cli.run(slicer.modules.brainsresample, None, params, wait_for_completion=True)
    logging.debug('resample labelmap through')
    slicer.mrmlScene.AddNode(outputVolume)

  @logmethod(logging.INFO)
  def onRegistrationResultStatusChanged(self, caller, event):
    self.skipAllUnregisteredPreviousSeries(self.currentResult.name)
    self._loading = getattr(self, "_loading", None)
    if self._loading:
      return
    self.save()
    self.invokeEvent(self.RegistrationStatusChangedEvent)

  @vtk.calldata_type(vtk.VTK_STRING)
  def onNewRegistrationResultCreated(self, caller, event, callData):
    self.currentResult = callData

  def skipAllUnregisteredPreviousSeries(self, series):
    selectedSeriesNumber = RegistrationResult.getSeriesNumberFromString(series)
    for series in [series for series in self.seriesList if not self.getSetting("COVER_TEMPLATE") in series]:
      currentSeriesNumber = RegistrationResult.getSeriesNumberFromString(series)
      if currentSeriesNumber < selectedSeriesNumber and self.isTrackingPossible(series):
        results = self.data.getResultsBySeriesNumber(currentSeriesNumber)
        if len(results) == 0:
          self.skipSeries(series)
      elif currentSeriesNumber >= selectedSeriesNumber:
        break

  def skipSeries(self, series):
    volume = self.getOrCreateVolumeForSeries(series)
    name, suffix = self.getRegistrationResultNameAndGeneratedSuffix(volume.GetName())
    result = self.data.createResult(name+suffix)
    result.volumes.fixed = volume
    result.skip()

  def skip(self, series):
    self.skipAllUnregisteredPreviousSeries(series)
    self.skipSeries(series)
    self.save()