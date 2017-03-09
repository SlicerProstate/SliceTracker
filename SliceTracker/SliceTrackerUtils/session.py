import os, logging
import vtk, ctk, ast
import shutil
from abc import ABCMeta, abstractmethod

import slicer
from sessionData import SessionData, RegistrationResult
from constants import SliceTrackerConstants
from exceptions import DICOMValueError

from SlicerProstateUtils.constants import DICOMTAGS
from SlicerProstateUtils.events import SlicerProstateEvents
from SlicerProstateUtils.helpers import IncomingDataWindow, SmartDICOMReceiver
from SlicerProstateUtils.mixins import ModuleLogicMixin


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
    self.invokeEvent(self.DirectoryChangedEvent, self.directory)

  def __init__(self):
    pass

  @abstractmethod
  def load(self):
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

  _steps = []
  trainingMode = False
  intraopDICOMReceiver = None
  loadableList = {}
  seriesList = []
  data = SessionData()

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

    self.zFrameRegistrationSuccessful = False

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

  def createNewCase(self, destination):
    # TODO: self.continueOldCase = False
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
    # TODO If case can be resumed !completed the user should be notified if he/she wants to do that. Otherwise readonly.
    filename = os.path.join(self.directory, SliceTrackerConstants.JSON_FILENAME)
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

    eligibleSeriesFiles = []
    for currentIndex, currentFile in enumerate(newFileList, start=1):
      # TODO: add statusbar
      self.invokeEvent(SlicerProstateEvents.NewFileIndexedEvent,
                       ["Indexing file %s" % currentFile, len(newFileList), currentIndex].__str__())
      slicer.app.processEvents()
      currentFile = os.path.join(self.intraopDICOMDirectory, currentFile)
      indexer.addFile(slicer.dicomDatabase, currentFile, None)
      series = self.makeSeriesNumberDescription(currentFile)
      if series:
        eligibleSeriesFiles.append(currentFile)
        if series not in self.seriesList:
          self.seriesList.append(series)
          self.loadableList[series] = self.createLoadableFileListForSeries(series)
    self.seriesList = sorted(self.seriesList, key=lambda s: RegistrationResult.getSeriesNumberFromString(s))

    if len(eligibleSeriesFiles):
      self.invokeEvent(SlicerProstateEvents.NewImageDataReceivedEvent, eligibleSeriesFiles.__str__())

  def deleteSeriesFromSeriesList(self, seriesNumber):
    for series in self.seriesList:
      currentSeriesNumber = RegistrationResult.getSeriesNumberFromString(series)
      if currentSeriesNumber == seriesNumber:
        self.seriesList.remove(series)

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

  def createLoadableFileListForSeries(self, series):
    seriesNumber = RegistrationResult.getSeriesNumberFromString(series)
    loadableList = []
    for dcm in self.getFileList(self.intraopDICOMDirectory):
      currentFile = os.path.join(self.intraopDICOMDirectory, dcm)
      currentSeriesNumber = int(self.getDICOMValue(currentFile, DICOMTAGS.SERIES_NUMBER))
      if currentSeriesNumber and currentSeriesNumber == seriesNumber:
        loadableList.append(currentFile)
    return loadableList