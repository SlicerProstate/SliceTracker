import os, logging
import vtk, ctk, ast
import shutil
from abc import ABCMeta, abstractmethod

import slicer
from sessionData import SessionData, RegistrationResult
from constants import SliceTrackerConstants

from exceptions import DICOMValueError, PreProcessedDataError

from SlicerProstateUtils.constants import DICOMTAGS, FileExtension
from SlicerProstateUtils.events import SlicerProstateEvents
from SlicerProstateUtils.helpers import IncomingDataWindow, SmartDICOMReceiver
from SlicerProstateUtils.mixins import ModuleLogicMixin

from SlicerProstateUtils.decorators import logmethod


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


class Singleton(object):

  __metaclass__ = ABCMeta

  def __new__(cls):
    if not hasattr(cls, 'instance'):
      cls.instance = super(Singleton, cls).__new__(cls)
    return cls.instance


class SliceTrackerSession(Singleton, SessionBase):

  # TODO: implement events that are invoked once data changes so that underlying steps can react to it
  IncomingDataSkippedEvent = SlicerProstateEvents.IncomingDataSkippedEvent
  IncomingPreopDataReceiveFinishedEvent = SlicerProstateEvents.IncomingDataReceiveFinishedEvent + 110

  IncomingIntraopDataReceiveFinishedEvent = SlicerProstateEvents.IncomingDataReceiveFinishedEvent + 111
  NewImageDataReceivedEvent = SlicerProstateEvents.NewImageDataReceivedEvent

  DICOMReceiverStatusChanged = SlicerProstateEvents.StatusChangedEvent
  DICOMReceiverStoppedEvent = SlicerProstateEvents.DICOMReceiverStoppedEvent

  NewCaseStartedEvent = vtk.vtkCommand.UserEvent + 501
  CloseCaseEvent = vtk.vtkCommand.UserEvent + 502

  CoverTemplateReceivedEvent = vtk.vtkCommand.UserEvent + 126
  CoverProstateReceivedEvent = vtk.vtkCommand.UserEvent + 127
  NeedleImageReceivedEvent = vtk.vtkCommand.UserEvent + 128
  VibeImageReceivedEvent = vtk.vtkCommand.UserEvent + 129
  OtherImageReceivedEvent = vtk.vtkCommand.UserEvent + 130

  ZFrameRegistrationSuccessfulEvent = vtk.vtkCommand.UserEvent + 140
  SuccessfullyPreprocessedEvent = vtk.vtkCommand.UserEvent + 141
  FailedPreprocessedEvent = vtk.vtkCommand.UserEvent + 142

  _steps = []
  _zFrameRegistrationSuccessful = False
  alreadyLoadedSeries = {}
  trainingMode = False
  intraopDICOMReceiver = None
  loadableList = {}
  seriesList = []
  data = SessionData()
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
    # was mpReviewPreprocessedOutput
    return os.path.join(self.directory, "mpReviewPreprocessed") if self.directory else None

  @property
  def preopDICOMDirectory(self):
    # was preopDICOMDataDirectory
    return os.path.join(self.directory, "DICOM", "Preop") if self.directory else None

  @property
  def intraopDICOMDirectory(self):
    # was intraopDICOMDataDirectory
    return os.path.join(self.directory, "DICOM", "Intraop") if self.directory else None

  @property
  def outputDirectory(self):
    # was outputDir
    return os.path.join(self.directory, "SliceTrackerOutputs")

  def isCaseDirectoryValid(self):
    return os.path.exists(self.preopDICOMDirectory) and os.path.exists(self.intraopDICOMDirectory)

  @property
  def zFrameRegistrationSuccessful(self):
    return self.data.zFrameTransform is not None and self._zFrameRegistrationSuccessful

  @zFrameRegistrationSuccessful.setter
  def zFrameRegistrationSuccessful(self, value):
    if value == self._zFrameRegistrationSuccessful:
      return
    self._zFrameRegistrationSuccessful = value
    if self._zFrameRegistrationSuccessful:
      self.save()
      self.invokeEvent(self.ZFrameRegistrationSuccessfulEvent)
      self.invokeEventForMostRecentEligibleSeries()

  def isPreProcessing(self):
    return slicer.util.selectedModule() != self.MODULE_NAME

  def __init__(self):
    super(SliceTrackerSession, self).__init__()

  def resetAndInitializeMembers(self):
    self.directory = None
    self.data = SessionData()
    self.trainingMode = False
    self.preopDICOMReceiver = None
    self.intraopDICOMReceiver = None
    self.loadableList = {}
    self.seriesList = []
    self.alreadyLoadedSeries = {}

  def __del__(self):
    pass

  def registerStep(self, step):
    logging.debug("Registering step %s" % step.NAME)
    if step not in self.steps:
      self.steps.append(step)

  def getStep(self, stepName):
    return next((x for x in self.steps if x.NAME == stepName), None)

  def isRunning(self):
    return self.directory is not None

  def clearData(self):
    self.resetAndInitializeMembers()

  @logmethod(logging.INFO)
  def processDirectory(self):
    self.newCaseCreated = getattr(self, "newCaseCreated", False)
    if self.newCaseCreated:
      return
    if not self.directory or not self.isCaseDirectoryValid():
      slicer.util.warningDisplay("The selected case directory seems not to be valid", windowTitle="SliceTracker")
      self.close(save=False)
    else:
      self.loadCaseData()

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
    self.invokeEvent(self.NewCaseStartedEvent)

  def close(self, save=False):
    if not self.isRunning():
      return
    if save:
      self.save()
    self.invokeEvent(self.CloseCaseEvent)
    self.resetAndInitializeMembers()

  def save(self):
    # TODO: not sure about each step .... saving its own data
    # for step in self.steps:
    #   step.save(self.directory)
    self.data.save(self.outputDirectory)

  def complete(self):
    self.data.completed = True
    self.close(save=True)

  def load(self):
    filename = os.path.join(self.outputDirectory, SliceTrackerConstants.JSON_FILENAME)
    if not os.path.exists(filename):
      return
    self.data.load(filename)
    coverProstate = self.data.getMostRecentApprovedCoverProstateRegistration()
    if coverProstate:
      if not self.data.initialVolume:
        self.data.initialVolume = coverProstate.movingVolume if self.data.usePreopData else coverProstate.fixedVolume
      self.data.initialTargets = coverProstate.originalTargets
      if self.data.usePreopData:  # TODO: makes sense?
        self.data.preopLabel = coverProstate.movingLabel
    if self.data.zFrameTransform:
      self._zFrameRegistrationSuccessful = True
    return True

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
    # TODO
    # self.intraopWatchBox.sourceFile = None
    self.resetPreopDICOMReceiver()
    logging.info("Starting DICOM Receiver for intra-procedural data")
    if not self.data.completed:
      self.stopIntraopDICOMReceiver()
      self.intraopDICOMReceiver = SmartDICOMReceiver(self.intraopDICOMDirectory)
      self._observeIntraopDICOMReceiverEvents()
      self.intraopDICOMReceiver.start(not self.trainingMode)
    else:
      self.invokeEvent(SlicerProstateEvents.DICOMReceiverStoppedEvent)
    self.importDICOMSeries(self.getFileList(self.intraopDICOMDirectory))
    if self.intraopDICOMReceiver:
      self.intraopDICOMReceiver.forceStatusChangeEvent()

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
      self.stopIntraopDICOMReceiver()

  def importDICOMSeries(self, newFileList):
    indexer = ctk.ctkDICOMIndexer()

    receivedFiles = []
    for currentIndex, currentFile in enumerate(newFileList, start=1):
      self.invokeEvent(SlicerProstateEvents.NewFileIndexedEvent,
                       ["Indexing file %s" % currentFile, len(newFileList), currentIndex].__str__())
      slicer.app.processEvents()
      currentFile = os.path.join(self.intraopDICOMDirectory, currentFile)
      indexer.addFile(slicer.dicomDatabase, currentFile, None)
      series = self.makeSeriesNumberDescription(currentFile)
      receivedFiles.append(currentFile)
      if series not in self.seriesList:
        self.seriesList.append(series)
        self.loadableList[series] = self.createLoadableFileListForSeries(series)
    self.seriesList = sorted(self.seriesList, key=lambda s: RegistrationResult.getSeriesNumberFromString(s))

    if len(receivedFiles):
      if self.data.usePreopData:
        self.verifyPatientIDEquality(receivedFiles)
      self.invokeEvent(SlicerProstateEvents.NewImageDataReceivedEvent, receivedFiles.__str__())
      self.invokeEventForMostRecentEligibleSeries()

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
        # TODO: remove files from filesystem self.loadableList[series] all files
        self.seriesList.remove(series)
        del self.loadableList[series]

  def stopIntraopDICOMReceiver(self):
    self.intraopDICOMReceiver = getattr(self, "dicomReceiver", None)
    if self.intraopDICOMReceiver:
      self.intraopDICOMReceiver.stop()
      self.intraopDICOMReceiver.removeEventObservers()

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

  def invokeEventForMostRecentEligibleSeries(self):
    if self.isPreProcessing():
      return
    event = self.NeedleImageReceivedEvent
    substring = self.getSetting("NEEDLE_IMAGE", moduleName=self.MODULE_NAME)

    if not self.data.getMostRecentApprovedCoverProstateRegistration():
      event = self.CoverProstateReceivedEvent
      substring = self.getSetting("COVER_PROSTATE", moduleName=self.MODULE_NAME)
      if not self.zFrameRegistrationSuccessful:
        event = self.CoverTemplateReceivedEvent
        substring = self.getSetting("COVER_TEMPLATE", moduleName=self.MODULE_NAME)
    series = self.getSeriesForSubstring(substring)

    if series and event:
      self.invokeEvent(event, series)

  def getSeriesForSubstring(self, substring):
    for series in reversed(self.seriesList):
      if substring in series:
        return series
    return None

  def loadPreProcessedData(self):
    try:
      preprocessedStudy = self.getFirstMpReviewPreprocessedStudy(self.preprocessedDirectory)
      self.loadPreopData(preprocessedStudy)
    except PreProcessedDataError:
      self.close(save=False)

  def loadCaseData(self):
    from mpReview import mpReviewLogic
    if os.path.exists(os.path.join(self.outputDirectory, SliceTrackerConstants.JSON_FILENAME)):
      if not self.openSavedSession():
        self.clearData()
    else:
      if mpReviewLogic.wasmpReviewPreprocessed(self.preprocessedDirectory):
        preprocessedStudy = self.getFirstMpReviewPreprocessedStudy(self.preprocessedDirectory)
        self.loadPreopData(preprocessedStudy)
      else:
        if len(os.listdir(self.preopDICOMDirectory)):
          self.startPreopDICOMReceiver()
        elif len(os.listdir(self.intraopDICOMDirectory)):
          self.data.usePreopData = False
          self.startIntraopDICOMReceiver()
        else:
          self.startPreopDICOMReceiver()
    # self.configureAllTargetDisplayNodes()

  def openSavedSession(self):
    self.load()
    if not slicer.util.confirmYesNoDisplay("A %s session has been found for the selected case. Do you want to %s?" \
              % ("completed" if self.data.completed else "started",
                 "open it" if self.data.completed else "continue this session")):
      return False
    self.data.resumed = True
    if self.data.usePreopData:
      preprocessedStudy = self.getFirstMpReviewPreprocessedStudy(self.preprocessedDirectory)
      self.loadPreopData(preprocessedStudy)
    else:
      if self.data.initialTargets:
        self.setupPreopLoadedTargets()
    self.startIntraopDICOMReceiver()
    return True

  def setupPreopLoadedTargets(self):
    pass
    # self.setTargetVisibility(self.logic.preopTargets, show=True)
    # self.targetTableModel.targetList = self.logic.preopTargets
    # self.fiducialSelector.setCurrentNode(self.logic.preopTargets)
    # self.logic.applyDefaultTargetDisplayNode(self.logic.preopTargets)
    # self.markupsLogic.JumpSlicesToNthPointInMarkup(self.logic.preopTargets.GetID(), 0)
    # self.targetTable.selectRow(0)
    # self.targetTable.enabled = True

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
      self.data.usedPreopData = True
      self.invokeEvent(self.SuccessfullyPreprocessedEvent)
      # self.movingLabelSelector.setCurrentNode(self.data.initialLabel)
      # self.logic.preopLabel.GetDisplayNode().SetAndObserveColorNodeID(self.mpReviewColorNode.GetID())
      #
      # self.configureRedSliceNodeForPreopData()
      # self.promptUserAndApplyBiasCorrectionIfNeeded()
      #
      # self.layoutManager.setLayout(self.LAYOUT_RED_SLICE_ONLY)
      # self.setAxialOrientation()
      # self.redSliceNode.RotateToVolumePlane(self.logic.preopVolume)
      # self.setupPreopLoadedTargets()

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
    segmentedColorName = self.getSetting("Segmentation_Color_Name", moduleName=self.MODULE_NAME)

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