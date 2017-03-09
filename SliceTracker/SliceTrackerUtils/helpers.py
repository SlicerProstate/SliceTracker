import os, datetime
import qt, vtk

from SlicerProstateUtils.mixins import ParameterNodeObservationMixin, ModuleWidgetMixin


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

