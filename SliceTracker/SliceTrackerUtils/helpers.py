from SlicerProstateUtils.mixins import ParameterNodeObservationMixin, ModuleLogicMixin, ModuleWidgetMixin
from SlicerProstateUtils.constants import FileExtension
from SlicerProstateUtils.decorators import multimethod, onExceptionReturnNone

from RegistrationData import RegistrationResults
from constants import SliceTrackerConstants

import vtk, qt, slicer
from collections import OrderedDict
import os, json, logging
import datetime


class SliceTrackerStepLogic(ModuleLogicMixin):

  def __init__(self, session):
    self.session = session

  def cleanup(self):
    raise NotImplementedError("This method needs to be implemented by all deriving classes")


class SliceTrackerStep(qt.QWidget, ModuleWidgetMixin):

  ActivatedEvent = vtk.vtkCommand.UserEvent + 150
  DeactivatedEvent = vtk.vtkCommand.UserEvent + 151

  NAME=None
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
    logging.info("%s %s" % ("activated" if self.active else "deactivate", self.NAME))
    self.invokeEvent(self.ActivatedEvent if self.active else self.DeactivatedEvent)
    method = "connect" if self.active else "disconnect"
    getattr(self.layoutManager.layoutChanged, method)(self.onLayoutChanged)
    logging.info("%s layout changed signal for %s" % (method, self.NAME))
  def __init__(self, session):
    qt.QWidget.__init__(self)
    assert self.LogicClass is not None, "Logic class for each SliceTrackerStep needs to be implemented"
    self.session = session
    self.logic = self.LogicClass(session)
    self.setLayout(qt.QGridLayout())
    self.setup()
    self.setupConnections()
    self._activated = False

  def __del__(self):
    self.removeEventObservers()

  def cleanup(self):
    pass

  def setup(self):
    raise NotImplementedError("This method needs to be implemented by all deriving classes")

  def setupConnections(self):
    pass
    # raise NotImplementedError

  def onLayoutChanged(self):
    raise NotImplementedError("This method needs to be implemented for %s" % self.NAME)


class SessionBase(ModuleLogicMixin):

  DirectoryChangedEvent = vtk.vtkCommand.UserEvent + 203

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

  def __init__(self, directory=None):
    self.directory = directory

  def load(self):
    raise NotImplementedError

  def save(self):
    raise NotImplementedError

  def close(self):
    self.save()


class Singleton(object):

  def __new__(cls):
    if not hasattr(cls, 'instance'):
      cls.instance = super(Singleton, cls).__new__(cls)
    return cls.instance


class SliceTrackerSession(Singleton, SessionBase):

  # TODO: implement events that are invoked once data changes so that underlying steps can react to it

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

  def __init__(self, directory=None):
    super(SliceTrackerSession, self).__init__(directory)
    self.regResults = RegistrationResults()
    self.completed = False
    self.usePreopData = None
    self.preopVolume = None
    self.preopLabel = None
    self.preopTargets = None
    self.trainingMode = False

    self.clippingModelNode = None
    self.inputMarkupNode = None

    self.biasCorrectionDone = False

    self.steps = []

  def __del__(self):
    pass

  def clearData(self):
    #TODO: implement
    pass

  def createNewCase(self, destination):
    # TODO: self.continueOldCase = False
    # TODO: make directory structure flexible
    self.directory = destination
    self.createDirectory(self.preopDICOMDirectory)
    self.createDirectory(self.intraopDICOMDirectory)
    self.createDirectory(self.preprocessedDirectory)
    self.createDirectory(self.outputDirectory)

  def closeCase(self):
    pass

  def registerStep(self, step):
    assert issubclass(step.__class__, SliceTrackerStep)
    if step not in self.steps:
      self.steps.append(step)

  def getStep(self, stepName):
    return next((x for x in self.steps if x.NAME == stepName), None)

  def save(self):
    for step in self.steps:
      step.save(self.directory)

  def saveSession(self, outputDir):
    if not os.path.exists(outputDir):
      self.createDirectory(outputDir)

    successfullySavedFileNames = []
    failedSaveOfFileNames = []

    def saveIntraopSegmentation():
      intraopLabel = self.regResults.intraopLabel
      if intraopLabel:
        seriesNumber = intraopLabel.GetName().split(":")[0]
        success, name = self.saveNodeData(intraopLabel, outputDir, FileExtension.NRRD, name=seriesNumber+"-LABEL",
                                          overwrite=True)
        self.handleSaveNodeDataReturn(success, name, successfullySavedFileNames, failedSaveOfFileNames)

        if self.clippingModelNode:
          success, name = self.saveNodeData(self.clippingModelNode, outputDir, FileExtension.VTK,
                                            name=seriesNumber+"-MODEL", overwrite=True)
          self.handleSaveNodeDataReturn(success, name, successfullySavedFileNames, failedSaveOfFileNames)

        if self.inputMarkupNode:
          success, name = self.saveNodeData(self.inputMarkupNode, outputDir, FileExtension.FCSV,
                                            name=seriesNumber+"-VolumeClip_points", overwrite=True)
          self.handleSaveNodeDataReturn(success, name, successfullySavedFileNames, failedSaveOfFileNames)

    def saveOriginalTargets():
      originalTargets = self.regResults.originalTargets
      if originalTargets:
        success, name = self.saveNodeData(originalTargets, outputDir, FileExtension.FCSV, name="PreopTargets",
                                          overwrite=True)
        self.handleSaveNodeDataReturn(success, name, successfullySavedFileNames, failedSaveOfFileNames)

    def saveBiasCorrectionResult():
      if not self.biasCorrectionDone:
        return None
      success, name = self.saveNodeData(self.preopVolume, outputDir, FileExtension.NRRD, overwrite=True)
      self.handleSaveNodeDataReturn(success, name, successfullySavedFileNames, failedSaveOfFileNames)
      return name+FileExtension.NRRD

    def saveZFrameTransformation():
      success, name = self.saveNodeData(self.zFrameTransform, outputDir, FileExtension.H5, overwrite=True)
      self.handleSaveNodeDataReturn(success, name, successfullySavedFileNames, failedSaveOfFileNames)
      return name+FileExtension.H5

    def createResultsDict():
      resultDict = OrderedDict()
      for result in self.regResults.getResultsAsList():
        resultDict.update(result.toDict())
      return resultDict

    def saveJSON(dictString):
      with open(os.path.join(outputDir, SliceTrackerConstants.JSON_FILENAME), 'w') as outfile:
        json.dump(dictString, outfile, indent=2)

    saveIntraopSegmentation()
    saveOriginalTargets()
    saveBiasCorrectionResult()

    savedSuccessfully, failedToSave = self.regResults.save(outputDir)
    successfullySavedFileNames += savedSuccessfully
    failedSaveOfFileNames += failedToSave

    saveJSON({"completed":self.completed,
              "usedPreopData":self.usePreopData,
              "VOLUME-PREOP-N4": saveBiasCorrectionResult(),
              "zFrameTransform": saveZFrameTransformation(),
              "results":createResultsDict()})

    if len(failedSaveOfFileNames):
      messageOutput = "The following data failed to saved:\n"
      for filename in failedSaveOfFileNames:
        messageOutput += filename + "\n"
      logging.debug(messageOutput)

    if len(successfullySavedFileNames):
      messageOutput = "The following data was successfully saved:\n"
      for filename in successfullySavedFileNames:
        messageOutput += filename + "\n"
      logging.debug(messageOutput)
    return len(failedSaveOfFileNames) == 0

  def complete(self):
    self.completed = True
    self.close()

  def load(self):
    filename = os.path.join(self.directory, SliceTrackerConstants.JSON_FILENAME)
    if not os.path.exists(filename):
      return
    with open(filename) as data_file:
      data = json.load(data_file)
      self.usePreopData = data["usedPreopData"]
      if data["VOLUME-PREOP-N4"]:
        self.loadBiasCorrectedImage(os.path.join(self.directory, data["VOLUME-PREOP-N4"]))
      self.loadZFrameTransform(os.path.join(self.directory, data["zFrameTransform"]))
    self.regResults.load(os.path.join(self.directory, SliceTrackerConstants.JSON_FILENAME))
    coverProstate = self.regResults.getMostRecentApprovedCoverProstateRegistration()
    if coverProstate:
      if not self.preopVolume:
        self.preopVolume = coverProstate.movingVolume if self.usePreopData else coverProstate.fixedVolume
      self.preopTargets = coverProstate.originalTargets
      if self.usePreopData:
        self.preopLabel = coverProstate.movingLabel
    return True

  def loadZFrameTransform(self, transformFile):
    self.zFrameRegistrationSuccessful = False
    if not os.path.exists(transformFile):
      return False
    success, self.zFrameTransform = slicer.util.loadTransform(transformFile, returnNode=True)
    self.zFrameRegistrationSuccessful = success
    # self.applyZFrameTransform(self.zFrameTransform)
    return success

  def loadBiasCorrectedImage(self, n4File):
    self.biasCorrectionDone = False
    if not os.path.exists(n4File):
      return False
    self.biasCorrectionDone = True
    success, self.preopVolume = slicer.util.loadVolume(n4File, returnNode=True)
    return success


class CustomTargetTableModel(qt.QAbstractTableModel, ParameterNodeObservationMixin):

  COLUMN_NAME = 'Name'
  COLUMN_2D_DISTANCE = 'Distance 2D[mm]'
  COLUMN_3D_DISTANCE = 'Distance 3D[mm]'
  COLUMN_HOLE = 'Hole'
  COLUMN_DEPTH = 'Depth [mm]'

  headers = [COLUMN_NAME, COLUMN_2D_DISTANCE, COLUMN_3D_DISTANCE, COLUMN_HOLE, COLUMN_DEPTH]

  @property
  def targetList(self):
    return self._targetList

  @targetList.setter
  def targetList(self, targetList):
    self.needleStartEndPositions = {}
    if self._targetList and self.observer:
      self._targetList.RemoveObserver(self.observer)
    self._targetList = targetList
    if self._targetList:
      self.observer = self._targetList.AddObserver(self._targetList.PointModifiedEvent, self.computeNewDepthAndHole)
    self.computeNewDepthAndHole()
    self.reset()

  @property
  def coverProstateTargetList(self):
    return self._coverProstateTargetList

  @coverProstateTargetList.setter
  def coverProstateTargetList(self, targetList):
    self._coverProstateTargetList = targetList
    #TODO: compute hole only if set

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
    self.needleStartEndPositions = {}
    self.targetList = targets
    self.computeCursorDistances = False
    self.zFrameDepths = {}
    self.zFrameHole = {}
    self.observer = None

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
    if role == qt.Qt.BackgroundRole:
      if index.row() % 2:
        return qt.QVariant(qt.QColor(qt.Qt.gray))
      else:
        return qt.QVariant(qt.QColor(qt.Qt.darkGray))

    if not index.isValid() or role not in [qt.Qt.DisplayRole, qt.Qt.ToolTipRole]:
      return None

    row = index.row()
    col = index.column()

    targetPosition = [0.0, 0.0, 0.0]
    if col in [1,2,3,4]:
      self.targetList.GetNthFiducialPosition(row, targetPosition)

    if col == 0:
      return self.targetList.GetNthFiducialLabel(row)
    elif (col == 1 or col == 2) and self.cursorPosition and self.computeCursorDistances:
      if col == 1:
        distance2D = self.logic.get3DDistance(targetPosition, self.cursorPosition)
        distance2D = [str(round(distance2D[0], 2)), str(round(distance2D[1], 2)), str(round(distance2D[2], 2))]
        return 'x=' + distance2D[0] + ' y=' + distance2D[1] + ' z=' + distance2D[2]
      distance3D = self.logic.get3DEuclideanDistance(targetPosition, self.cursorPosition)
      return str(round(distance3D, 2))

    elif (col == 3 or col == 4) and self.logic.zFrameRegistrationSuccessful:
      if col == 3:
        return self.computeZFrameHole(row, targetPosition)
      else:
        return self.computeZFrameDepth(row, targetPosition)
    return ""

  def computeZFrameHole(self, index, targetPosition):
    if index not in self.zFrameHole.keys():
      (start, end, indexX, indexY, depth, inRange) = self.logic.computeNearestPath(targetPosition)
      self.needleStartEndPositions[index] = (start, end)
      self.zFrameHole[index] = '(%s, %s)' % (indexX, indexY)
    return self.zFrameHole[index]

  def computeZFrameDepth(self, index, targetPosition):
    if index not in self.zFrameDepths.keys():
      (start, end, indexX, indexY, depth, inRange) = self.logic.computeNearestPath(targetPosition)
      self.zFrameDepths[index] = '%.3f' % depth if inRange else '(%.3f)' % depth
    return self.zFrameDepths[index]

  def computeNewDepthAndHole(self, observer=None, caller=None):
    self.zFrameDepths = {}
    self.zFrameHole = {}
    if not self.targetList or not self.logic.zFrameRegistrationSuccessful:
      return

    for index in range(self.targetList.GetNumberOfFiducials()):
      pos = [0.0, 0.0, 0.0]
      self.targetList.GetNthFiducialPosition(index, pos)
      self.computeZFrameHole(index, pos)

    self.dataChanged(self.index(0, 3), self.index(self.rowCount()-1, 4))
    self.invokeEvent(vtk.vtkCommand.ModifiedEvent)


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

