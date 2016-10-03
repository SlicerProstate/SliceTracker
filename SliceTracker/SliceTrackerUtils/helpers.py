from SlicerProstateUtils.mixins import ParameterNodeObservationMixin, ModuleLogicMixin, ModuleWidgetMixin
from SlicerProstateUtils.constants import FileExtension
from SlicerProstateUtils.decorators import multimethod


from data import RegistrationResults
from constants import SliceTrackerConstants

import vtk, qt, slicer
from collections import OrderedDict
import os, json, logging


class SliceTrackerStep(qt.QGroupBox, ModuleWidgetMixin):

  @property
  def active(self):
    return self._active

  @active.setter
  def active(self, value):
    self._active = value

  def __init__(self, parent=None):
    qt.QGroupBox.__init__(self, parent)
    self._active = False
    self.setLayout(qt.QGridLayout())
    self.setup()

  def cleanup(self):
    pass

  def setup(self):
    raise NotImplementedError("This method needs to be implemented by all deriving classes")

  def setupConnections(self):
    self.layoutManager.layoutChanged.connect(self.onLayoutChanged)

  def onLayoutChanged(self):
    raise NotImplementedError("This method needs to be implemented by all deriving classes")


class SessionBase(ModuleLogicMixin):

  @property
  def directory(self):
    return self._directory

  @directory.setter
  def directory(self, value):
    if not value:
      raise ValueError("You cannot assign None to the session directory")
    if not os.path.exists(value):
      self.createDirectory(value)
    self._directory = value

  def __init__(self, directory):
    self.directory = directory

  def load(self):
    raise NotImplementedError

  def save(self):
    raise NotImplementedError

  def close(self):
    self.save()


class SliceTrackerSession(SessionBase):

  def __init__(self, directory):
    super(SliceTrackerSession, self).__init__(directory)
    self.regResults = RegistrationResults()
    self.completed = False
    self.usePreopData = None
    self.preopVolume = None
    self.preopLabel = None
    self.preopTargets = None

    self.clippingModelNode = None
    self.inputMarkupNode = None

    self.biasCorrectionDone = False

    self.steps = []

  def __del__(self):
    pass

  @multimethod(SliceTrackerStep)
  def register(self, step):
    if step not in self.steps:
      self.steps.append(step)

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