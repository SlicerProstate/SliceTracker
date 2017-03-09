from SlicerProstateUtils.mixins import ParameterNodeObservationMixin, ModuleLogicMixin, ModuleWidgetMixin
from SlicerProstateUtils.constants import DICOMTAGS
from SlicerProstateUtils.events import SlicerProstateEvents
from exceptions import DICOMValueError
from SlicerProstateUtils.helpers import SmartDICOMReceiver, IncomingDataWindow
from SlicerProstateUtils.decorators import logmethod

from RegistrationData import RegistrationResults, RegistrationResult
from constants import SliceTrackerConstants

import ctk, vtk, qt, slicer
import os, logging
import datetime

from abc import abstractmethod, ABCMeta


class SliceTrackerStepLogic(ModuleLogicMixin):

  __metaclass__ = ABCMeta

  def __init__(self):
    self.session = SliceTrackerSession()

  @abstractmethod
  def cleanup(self):
    pass


class SliceTrackerStep(qt.QWidget, ModuleWidgetMixin):

  ActivatedEvent = vtk.vtkCommand.UserEvent + 150
  DeactivatedEvent = vtk.vtkCommand.UserEvent + 151

  NAME = None
  MODULE_NAME = "SliceTracker"

  LogicClass = None

  @property
  def active(self):
    return self._activated

  @active.setter
  def active(self, value):
    if self.active == value:
      return
    self._activated = value
    logging.debug("%s %s" % ("activated" if self.active else "deactivate", self.NAME))
    self.invokeEvent(self.ActivatedEvent if self.active else self.DeactivatedEvent)
    if self.active:
      self.layoutManager.layoutChanged.connect(self.onLayoutChanged)
      self.setupSessionObservers()
    else:
      self.layoutManager.layoutChanged.disconnect(self.onLayoutChanged)
      self.removeSessionEventObservers()

  def __init__(self):
    qt.QWidget.__init__(self)
    assert self.LogicClass is not None, "Logic class for each SliceTrackerStep needs to be implemented"
    self.session = SliceTrackerSession()
    self.logic = self.LogicClass()
    self.setLayout(qt.QGridLayout())
    self.setup()
    self.setupConnections()
    self._activated = False

  def setupSessionObservers(self):
    self.session.addEventObserver(self.session.NewCaseStartedEvent, self.onNewCaseStarted)
    self.session.addEventObserver(self.session.CloseCaseEvent, self.onCaseClosed)

  def removeSessionEventObservers(self):
    self.session.removeEventObserver(self.session.NewCaseStartedEvent, self.onNewCaseStarted)
    self.session.removeEventObserver(self.session.CloseCaseEvent, self.onCaseClosed)

  @logmethod(logging.INFO)
  def onNewCaseStarted(self, caller, event):
    pass

  @logmethod(logging.INFO)
  def onCaseClosed(self, caller, event):
    pass

  def __del__(self):
    self.removeEventObservers()

  def cleanup(self):
    raise NotImplementedError("This method needs to be implemented for %s" % self.NAME)

  def setup(self):
    NotImplementedError("This method needs to be implemented for %s" % self.NAME)

  def setupConnections(self):
    NotImplementedError("This method needs to be implemented for %s" % self.NAME)

  def onLayoutChanged(self):
    raise NotImplementedError("This method needs to be implemented for %s" % self.NAME)


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
  IncomingDataReceiveFinishedEvent = SlicerProstateEvents.IncomingDataReceiveFinishedEvent
  DICOMReceiverStatusChanged = SlicerProstateEvents.StatusChangedEvent
  DICOMReceiverStoppedEvent = SlicerProstateEvents.DICOMReceiverStoppedEvent

  NewCaseStartedEvent = vtk.vtkCommand.UserEvent + 501
  CloseCaseEvent = vtk.vtkCommand.UserEvent + 502

  _steps = []
  trainingMode = False
  intraopDICOMReceiver = None
  loadableList = {}
  seriesList = []
  regResults = RegistrationResults()

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
    self.regResults = RegistrationResults()
    self.trainingMode = False
    self.preopDICOMReceiver = None
    self.intraopDICOMReceiver = None
    self.loadableList = {}
    self.seriesList = []

  def __del__(self):
    pass

  def registerStep(self, step):
    assert issubclass(step.__class__, SliceTrackerStep)
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
    # TODO: make directory structure flexible
    self.resetAndInitializeMembers()
    self.directory = destination
    self.createDirectory(self.preopDICOMDirectory)
    self.createDirectory(self.intraopDICOMDirectory)
    self.createDirectory(self.preprocessedDirectory)
    self.createDirectory(self.outputDirectory)
    self.invokeEvent(self.NewCaseStartedEvent)
    self.startPreopDICOMReceiver()

  def close(self, save=False):
    if save:
      self.save()
    self.directory = None
    self.invokeEvent(self.CloseCaseEvent)
    self.resetAndInitializeMembers()

  def save(self):
    # TODO: not sure about each step .... saving its own data
    for step in self.steps:
      step.save(self.directory)
    self.regResults.save(self.outputDirectory)

  def complete(self):
    self.regResults.completed = True
    self.close(save=True)

  def load(self):
    # TODO If case can be resumed !completed the user should be notified if he/she wants to do that. Otherwise readonly.
    filename = os.path.join(self.directory, SliceTrackerConstants.JSON_FILENAME)
    if not os.path.exists(filename):
      return
    self.regResults.load(filename)
    coverProstate = self.regResults.getMostRecentApprovedCoverProstateRegistration()
    if coverProstate:
      if not self.regResults.initialVolume:
        self.regResults.initialVolume = coverProstate.movingVolume if self.regResults.usePreopData else coverProstate.fixedVolume
      self.regResults.initialTargets = coverProstate.originalTargets
      if self.regResults.usePreopData:  # TODO: makes sense?
        self.regResults.preopLabel = coverProstate.movingLabel
    return True

  def startPreopDICOMReceiver(self):
    self.resetPreopDICOMReceiver()
    self.preopDICOMReceiver = IncomingDataWindow(incomingDataDirectory=self.preopDICOMDirectory,
                                                 skipText="No preoperative images available")
    self.preopDICOMReceiver.addEventObserver(SlicerProstateEvents.IncomingDataSkippedEvent,
                                             self.onSkippingPreopDataReception)
    self.preopDICOMReceiver.addEventObserver(SlicerProstateEvents.IncomingDataCanceledEvent,
                                             lambda caller, event: self.clearData())
    self.preopDICOMReceiver.addEventObserver(SlicerProstateEvents.IncomingDataReceiveFinishedEvent,
                                             self.onPreopDataReceptionFinished)
    self.preopDICOMReceiver.show()

  def onSkippingPreopDataReception(self, caller, event):
    self.regResults.usePreopData = False
    self.resetPreopDICOMReceiver()
    self.startIntraopDICOMReceiver()

  def onPreopDataReceptionFinished(self, caller, event):
    self.regResults.usePreopData = True
    self.resetPreopDICOMReceiver()
    self.startIntraopDICOMReceiver()

  def resetPreopDICOMReceiver(self):
    if self.preopDICOMReceiver:
      self.preopDICOMReceiver.hide()
      self.preopDICOMReceiver.removeEventObservers()
      self.preopDICOMReceiver = None

  def startIntraopDICOMReceiver(self):
    # TODO
    # self.intraopWatchBox.sourceFile = None
    logging.info("Starting DICOM Receiver for intra-procedural data")
    if not self.regResults.completed:
      self.stopIntraopDICOMReceiver()
      self.intraopDICOMReceiver = SmartDICOMReceiver(self.intraopDICOMDirectory)
      # self._observeIntraopDICOMReceiverEvents()
      self.intraopDICOMReceiver.start(not self.trainingMode)
    else:
      self.invokeEvent(SlicerProstateEvents.DICOMReceiverStoppedEvent)
    self.importDICOMSeries(self.getFileList(self.intraopDICOMDirectory))
    if self.intraopDICOMReceiver:
      self.intraopDICOMReceiver.forceStatusChangeEvent()

  def _observeIntraopDICOMReceiverEvents(self):
    self.intraopDICOMReceiver.addEventObserver(self.intraopDICOMReceiver.IncomingDataReceiveFinishedEvent,
                                               self.onDICOMSeriesReceived)
    self.intraopDICOMReceiver.addEventObserver(SlicerProstateEvents.StatusChangedEvent,
                                               self.onDICOMReceiverStatusChanged)
    self.intraopDICOMReceiver.addEventObserver(SlicerProstateEvents.DICOMReceiverStoppedEvent,
                                               self.onSmartDICOMReceiverStopped)

    # self.logic.addEventObserver(SlicerProstateEvents.StatusChangedEvent, self.onDICOMReceiverStatusChanged)
    # self.logic.addEventObserver(SlicerProstateEvents.DICOMReceiverStoppedEvent, self.onIntraopDICOMReceiverStopped)
    # self.logic.addEventObserver(SlicerProstateEvents.NewImageDataReceivedEvent, self.onNewImageDataReceived)
    # self.logic.addEventObserver(SlicerProstateEvents.NewFileIndexedEvent, self.onNewFileIndexed)

  def stopIntraopDICOMReceiver(self):
    self.intraopDICOMReceiver = getattr(self, "dicomReceiver", None)
    if self.intraopDICOMReceiver:
      self.intraopDICOMReceiver.stop()
      self.intraopDICOMReceiver.removeEventObservers()

  def importDICOMSeries(self, newFileList):
    indexer = ctk.ctkDICOMIndexer()

    eligibleSeriesFiles = []
    size = len(newFileList)
    for currentIndex, currentFile in enumerate(newFileList, start=1):
      self.invokeEvent(SlicerProstateEvents.NewFileIndexedEvent,
                       ["Indexing file %s" % currentFile, size, currentIndex].__str__())
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


class CustomTargetTableModel(qt.QAbstractTableModel, ParameterNodeObservationMixin):

  PLANNING_IMAGE_NAME = "Initial registration"

  COLUMN_NAME = 'Name'
  COLUMN_DISTANCE = 'Distance[cm]'
  COLUMN_HOLE = 'Hole'
  COLUMN_DEPTH = 'Depth[cm]'

  headers = [COLUMN_NAME, COLUMN_DISTANCE, COLUMN_HOLE, COLUMN_DEPTH]

  @property
  def targetList(self):
    return self._targetList

  @targetList.setter
  def targetList(self, targetList):
    self._targetList = targetList
    if self.currentGuidanceComputation and self.observer:
      self.self.currentGuidanceComputation.RemoveObserver(self.observer)
    self.currentGuidanceComputation = self.getOrCreateNewGuidanceComputation(targetList)
    if self.currentGuidanceComputation:
      self.observer = self.currentGuidanceComputation.addEventObserver(vtk.vtkCommand.ModifiedEvent, self.updateHoleAndDepth)
    self.reset()

  @property
  def coverProstateTargetList(self):
    return self._coverProstateTargetList

  @coverProstateTargetList.setter
  def coverProstateTargetList(self, targetList):
    self._coverProstateTargetList = targetList

  @property
  def cursorPosition(self):
    return self._cursorPosition

  @cursorPosition.setter
  def cursorPosition(self, cursorPosition):
    self._cursorPosition = cursorPosition
    self.dataChanged(self.index(0, 1), self.index(self.rowCount()-1, 2))

  def __init__(self, logic, targets=None, parent=None, *args):
    qt.QAbstractTableModel.__init__(self, parent, *args)
    self.logic = logic
    self._cursorPosition = None
    self._targetList = None
    self._guidanceComputations = []
    self.currentGuidanceComputation = None
    self.targetList = targets
    self.computeCursorDistances = False
    self.currentTargetIndex = -1
    self.observer = None

  def getOrCreateNewGuidanceComputation(self, targetList):
    if not targetList:
      return None
    guidance = None
    for crntGuidance in self._guidanceComputations:
      if crntGuidance.targetList is targetList:
        guidance = crntGuidance
        break
    if not guidance:
      self._guidanceComputations.append(ZFrameGuidanceComputation(targetList, self))
      guidance = self._guidanceComputations[-1]
    if self._targetList is targetList:
      self.updateHoleAndDepth()
    return guidance

  def updateHoleAndDepth(self, caller=None, event=None):
    self.dataChanged(self.index(0, 3), self.index(self.rowCount() - 1, 4))
    self.invokeEvent(vtk.vtkCommand.ModifiedEvent)

  def headerData(self, col, orientation, role):
    if orientation == qt.Qt.Horizontal and role in [qt.Qt.DisplayRole, qt.Qt.ToolTipRole]:
        return self.headers[col]
    return None

  def rowCount(self):
    try:
      number_of_targets = self.targetList.GetNumberOfFiducials()
      return number_of_targets
    except AttributeError:
      return 0

  def columnCount(self):
    return len(self.headers)

  def data(self, index, role):
    result = self.getBackgroundOrToolTipData(index, role)
    if result:
      return result

    row = index.row()
    col = index.column()

    if not index.isValid() or role not in [qt.Qt.DisplayRole, qt.Qt.ToolTipRole]:
      return None

    if col == 0:
      return self.targetList.GetNthFiducialLabel(row)

    if col == 1 and self.cursorPosition and self.computeCursorDistances and self.currentTargetIndex == row:
      targetPosition = self.logic.getTargetPosition(self.targetList, row)
      distance2D = self.logic.get3DDistance(targetPosition, self.cursorPosition)
      distance2D = [str(round(distance2D[0]/10, 1)), str(round(distance2D[1]/10, 1)), str(round(distance2D[2]/10, 1))]
      distance3D = self.logic.get3DEuclideanDistance(targetPosition, self.cursorPosition)
      text = 'x= ' + distance2D[0] + '  y= ' + distance2D[1] + '  z= ' + distance2D[2] + '  (3D= ' + str(round(distance3D/10, 1)) + ')'
      return text
    elif col == 2 and self.logic.zFrameRegistrationSuccessful:
      return self.currentGuidanceComputation.getZFrameHole(row)
    elif col == 3 and self.logic.zFrameRegistrationSuccessful:
      return self.currentGuidanceComputation.getZFrameDepth(row)
    return ""

  def getBackgroundOrToolTipData(self, index, role):
    if role not in [qt.Qt.BackgroundRole, qt.Qt.ToolTipRole]:
      return None
    backgroundRequested = role == qt.Qt.BackgroundRole
    row = index.row()
    col = index.column()
    outOfRangeText = "" if self.currentGuidanceComputation.getZFrameDepthInRange(row) else "Current depth: out of range"
    if self.coverProstateTargetList and not self.coverProstateTargetList is self.targetList:
      if col in [2, 3]:
        coverProstateGuidance = self.getOrCreateNewGuidanceComputation(self.coverProstateTargetList)
        if col == 2:
          coverProstateHole = coverProstateGuidance.getZFrameHole(row)
          if self.currentGuidanceComputation.getZFrameHole(row) == coverProstateHole:
            return qt.QColor(qt.Qt.green) if backgroundRequested else ""
          else:
            return qt.QColor(qt.Qt.red) if backgroundRequested else "{} hole: {}".format(self.PLANNING_IMAGE_NAME, coverProstateHole)
        elif col == 3:
          currentDepth = self.currentGuidanceComputation.getZFrameDepth(row, asString=False)
          coverProstateDepth = coverProstateGuidance.getZFrameDepth(row, asString=False)
          if abs(currentDepth - coverProstateDepth) <= max(1e-9 * max(abs(currentDepth), abs(coverProstateDepth)), 0.5):
            if backgroundRequested:
              return qt.QColor(qt.Qt.red) if len(outOfRangeText) else qt.QColor(qt.Qt.green)
            return "%s depth: '%.1f' %s" % (self.PLANNING_IMAGE_NAME, coverProstateDepth, "\n"+outOfRangeText)
          else:
            if backgroundRequested:
              return qt.QColor(qt.Qt.red)
            return "%s depth: '%.1f' %s" % (self.PLANNING_IMAGE_NAME, coverProstateDepth, "\n"+outOfRangeText)
    elif self.coverProstateTargetList is self.targetList and col == 3:
      if backgroundRequested and len(outOfRangeText):
        return qt.QColor(qt.Qt.red)
      elif len(outOfRangeText):
        return outOfRangeText
    return None


class ZFrameGuidanceComputation(ParameterNodeObservationMixin):

  SUPPORTED_EVENTS = [vtk.vtkCommand.ModifiedEvent]

  @property
  def logic(self):
    return self.parent.logic

  def __init__(self, targetList, parent):
    self.targetList = targetList
    self.parent = parent
    self.observer = self.targetList.AddObserver(self.targetList.PointModifiedEvent, self.calculate)
    self.reset()
    self.calculate()

  def __del__(self):
    if self.targetList and self.observer:
      self.targetList.RemoveObserver(self.observer)

  def reset(self):
    self.needleStartEndPositions = {}
    self.computedHoles = {}
    self.computedDepth = {}

  def calculate(self, caller=None, event=None):
    if not self.targetList or not self.logic.zFrameRegistrationSuccessful:
      return
    for index in range(self.targetList.GetNumberOfFiducials()):
      self.calculateZFrameHoleAndDepth(index)
    self.invokeEvent(vtk.vtkCommand.ModifiedEvent)

  def getZFrameHole(self, index):
    if index not in self.computedHoles.keys():
      self.calculateZFrameHoleAndDepth(index)
    return '(%s, %s)' % (self.computedHoles[index][0], self.computedHoles[index][1])

  def getZFrameDepth(self, index, asString=True):
    if index not in self.computedHoles.keys():
      self.calculateZFrameHoleAndDepth(index)
    if asString:
      return '%.1f' % self.computedDepth[index][1] if self.computedDepth[index][0] else '(%.1f)' % self.computedDepth[index][1]
    else:
      return self.computedDepth[index][1]

  def getZFrameDepthInRange(self, index):
    if index not in self.computedHoles.keys():
      self.calculateZFrameHoleAndDepth(index)
    return self.computedDepth[index][0]

  def calculateZFrameHoleAndDepth(self, index):
    targetPosition = self.logic.getTargetPosition(self.targetList, index)
    (start, end, indexX, indexY, depth, inRange) = self.logic.computeNearestPath(targetPosition)
    self.needleStartEndPositions[index] = (start, end)
    self.computedHoles[index] = [indexX, indexY]
    self.computedDepth[index] = [inRange, round(depth/10, 1)]


class NewCaseSelectionNameWidget(qt.QMessageBox, ModuleWidgetMixin):

  PREFIX = "Case"
  SUFFIX = "-" + datetime.date.today().strftime("%Y%m%d")
  SUFFIX_PATTERN = "-[0-9]{8}"
  CASE_NUMBER_DIGITS = 3
  PATTERN = PREFIX+"[0-9]{"+str(CASE_NUMBER_DIGITS-1)+"}[0-9]{1}"+SUFFIX_PATTERN

  def __init__(self, destination, parent=None):
    super(NewCaseSelectionNameWidget, self).__init__(parent)
    if not os.path.exists(destination):
      raise
    self.destinationRoot = destination
    self.newCaseDirectory = None
    self.minimum = self.getNextCaseNumber()
    self.setupUI()
    self.setupConnections()
    self.onCaseNumberChanged(self.minimum)

  def getNextCaseNumber(self):
    import re
    caseNumber = 0
    for dirName in [dirName for dirName in os.listdir(self.destinationRoot)
                     if os.path.isdir(os.path.join(self.destinationRoot, dirName)) and re.match(self.PATTERN, dirName)]:
      number = int(re.split(self.SUFFIX_PATTERN, dirName)[0].split(self.PREFIX)[1])
      caseNumber = caseNumber if caseNumber > number else number
    return caseNumber+1

  def setupUI(self):
    self.setWindowTitle("Case Number Selection")
    self.setText("Please select a case number for the new case.")
    self.setIcon(qt.QMessageBox.Question)
    self.spinbox = qt.QSpinBox()
    self.spinbox.setRange(self.minimum, int("9"*self.CASE_NUMBER_DIGITS))
    self.preview = qt.QLabel()
    self.notice = qt.QLabel()
    self.layout().addWidget(self.createVLayout([self.createHLayout([qt.QLabel("Proposed Case Number"), self.spinbox]),
                                                self.preview, self.notice]), 2, 1)
    self.okButton = self.addButton(self.Ok)
    self.okButton.enabled = False
    self.cancelButton = self.addButton(self.Cancel)
    self.setDefaultButton(self.okButton)

  def setupConnections(self):
    self.spinbox.valueChanged.connect(self.onCaseNumberChanged)

  def onCaseNumberChanged(self, caseNumber):
    formatString = '%0'+str(self.CASE_NUMBER_DIGITS)+'d'
    caseNumber = formatString % caseNumber
    directory = self.PREFIX+caseNumber+self.SUFFIX
    self.newCaseDirectory = os.path.join(self.destinationRoot, directory)
    self.preview.setText("New case directory: " + self.newCaseDirectory)
    self.okButton.enabled = not os.path.exists(self.newCaseDirectory)
    self.notice.text = "" if not os.path.exists(self.newCaseDirectory) else "Note: Directory already exists."

