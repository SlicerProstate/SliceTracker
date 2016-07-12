from SlicerProstateUtils.mixins import ParameterNodeObservationMixin
import vtk, qt


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