import qt
import vtk
import numpy
import logging
from ...constants import SliceTrackerConstants as constants
from ..base import SliceTrackerPlugin, SliceTrackerLogicBase
from ..zFrameRegistration import SliceTrackerZFrameRegistrationStepLogic
from ...session import SliceTrackerSession

from SlicerDevelopmentToolboxUtils.mixins import ModuleLogicMixin
from SlicerDevelopmentToolboxUtils.decorators import logmethod, onModuleSelected
from SlicerDevelopmentToolboxUtils.helpers import SliceAnnotation


class CustomTargetTableModel(qt.QAbstractTableModel, ModuleLogicMixin):

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
      self.observer = self.currentGuidanceComputation.addEventObserver(vtk.vtkCommand.ModifiedEvent,
                                                                       self.updateHoleAndDepth)
    self.reset()

  @property
  def coverProstateTargetList(self):
    self._coverProstateTargetList = getattr(self, "_coverProstateTargetList", None)
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
    self.session = SliceTrackerSession()
    self.logic = logic
    self._cursorPosition = None
    self._targetList = None
    self._guidanceComputations = []
    self.currentGuidanceComputation = None
    self.targetList = targets
    self.computeCursorDistances = False
    self.currentTargetIndex = -1
    self.observer = None
    self.session.addEventObserver(self.session.ZFrameRegistrationSuccessfulEvent, self.onZFrameRegistrationSuccessful)

  def getOrCreateNewGuidanceComputation(self, targetList):
    if not targetList:
      return None
    guidance = None
    for crntGuidance in self._guidanceComputations:
      if crntGuidance.targetList is targetList:
        guidance = crntGuidance
        break
    if not guidance:
      self._guidanceComputations.append(ZFrameGuidanceComputation(targetList))
      guidance = self._guidanceComputations[-1]
    if self._targetList is targetList:
      self.updateHoleAndDepth()
    return guidance

  def onZFrameRegistrationSuccessful(self, caller, event):
    self._guidanceComputations = []

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
      text = 'x= ' + distance2D[0] + '  y= ' + distance2D[1] + \
             '  z= ' + distance2D[2] + '  (3D= ' + str(round(distance3D/10, 1)) + ')'
      return text
    elif col == 2 and self.session.zFrameRegistrationSuccessful:
      return self.currentGuidanceComputation.getZFrameHole(row)
    elif col == 3 and self.session.zFrameRegistrationSuccessful:
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
            return qt.QColor(qt.Qt.red) if backgroundRequested else "{} hole: {}".format(self.PLANNING_IMAGE_NAME,
                                                                                         coverProstateHole)
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


class ZFrameGuidanceComputation(ModuleLogicMixin):

  SUPPORTED_EVENTS = [vtk.vtkCommand.ModifiedEvent]

  def __init__(self, targetList):
    self.session = SliceTrackerSession()
    self.zFrameRegistration = SliceTrackerZFrameRegistrationStepLogic()
    self.targetList = targetList
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
    if not self.targetList or not self.session.zFrameRegistrationSuccessful:
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
      return '%.1f' % self.computedDepth[index][1] if self.computedDepth[index][0] else \
        '(%.1f)' % self.computedDepth[index][1]
    else:
      return self.computedDepth[index][1]

  def getZFrameDepthInRange(self, index):
    if index not in self.computedHoles.keys():
      self.calculateZFrameHoleAndDepth(index)
    return self.computedDepth[index][0]

  def calculateZFrameHoleAndDepth(self, index):
    targetPosition = self.getTargetPosition(self.targetList, index)
    (start, end, indexX, indexY, depth, inRange) = self.computeNearestPath(targetPosition)
    logging.debug("start:{}, end:{}, indexX:{}, indexY:{}, depth:{}, inRange:{}".format(start, end, indexX, indexY, depth, inRange))
    self.needleStartEndPositions[index] = (start, end)
    self.computedHoles[index] = [indexX, indexY]
    self.computedDepth[index] = [inRange, round(depth/10, 1)]

  def computeNearestPath(self, pos):
    minMag2 = numpy.Inf
    minDepth = 0.0
    minIndex = -1
    needleStart = None
    needleEnd = None

    p = numpy.array(pos)
    for i, orig in enumerate(self.zFrameRegistration.pathOrigins):
      vec = self.zFrameRegistration.pathVectors[i]
      op = p - orig
      aproj = numpy.inner(op, vec)
      perp = op-aproj*vec
      mag2 = numpy.vdot(perp, perp)
      if mag2 < minMag2:
        minMag2 = mag2
        minIndex = i
        minDepth = aproj
      i += 1

    indexX = '--'
    indexY = '--'
    inRange = False

    if minIndex != -1:
      indexX = self.zFrameRegistration.templateIndex[minIndex][0]
      indexY = self.zFrameRegistration.templateIndex[minIndex][1]
      if 0 < minDepth < self.zFrameRegistration.templateMaxDepth[minIndex]:
        inRange = True
        needleStart, needleEnd = self.getNeedleStartEndPointFromPathOrigins(minIndex)
      # else:
      #   self.zFrameRegistration.removeNeedleModelNode()

    return needleStart, needleEnd, indexX, indexY, minDepth, inRange

  def getNeedleStartEndPointFromPathOrigins(self, index):
    start = self.zFrameRegistration.pathOrigins[index]
    v = self.zFrameRegistration.pathVectors[index]
    nl = numpy.linalg.norm(v)
    n = v / nl  # normal vector
    l = self.zFrameRegistration.templateMaxDepth[index]
    end = start + l * n
    return start, end


class SliceTrackerTargetTableLogic(SliceTrackerLogicBase):

  def __init__(self):
    super(SliceTrackerTargetTableLogic, self).__init__()

  def setTargetSelected(self, targetNode, selected=False):
    self.markupsLogic.SetAllMarkupsSelected(targetNode, selected)


class SliceTrackerTargetTablePlugin(SliceTrackerPlugin):

  NAME = "TargetTable"
  LogicClass = SliceTrackerTargetTableLogic

  @property
  def lastSelectedModelIndex(self):
    return self.session.lastSelectedModelIndex

  @lastSelectedModelIndex.setter
  def lastSelectedModelIndex(self, modelIndex):
    assert self.currentTargets is not None
    self.session.lastSelectedModelIndex = modelIndex

  @property
  def movingEnabled(self):
    self._movingEnabled = getattr(self, "_movingEnabled", False)
    return self._movingEnabled

  @movingEnabled.setter
  def movingEnabled(self, value):
    if self.movingEnabled  == value:
      return
    self._movingEnabled = value
    if self.movingEnabled:
      self.targetTable.connect('doubleClicked(QModelIndex)', self.onMoveTargetRequest)
    else:
      self.targetTable.disconnect('doubleClicked(QModelIndex)', self.onMoveTargetRequest)

  @property
  def currentTargets(self):
    self._currentTargets = getattr(self, "_currentTargets", None)
    return self._currentTargets

  @currentTargets.setter
  def currentTargets(self, targets):
    self.disableTargetMovingMode()
    self._currentTargets = targets
    self.targetTableModel.targetList = targets
    if not targets:
      self.targetTableModel.coverProstateTargetList = None
    else:
      coverProstate = self.session.data.getMostRecentApprovedCoverProstateRegistration()
      if coverProstate:
        self.targetTableModel.coverProstateTargetList = coverProstate.targets.approved
    self.targetTable.enabled = targets is not None
    if self.currentTargets:
      self.onTargetSelectionChanged()

  def __init__(self, **kwargs):
    super(SliceTrackerTargetTablePlugin, self).__init__()
    self.movingEnabled = kwargs.pop("movingEnabled", False)
    self.keyPressEventObservers = {}
    self.keyReleaseEventObservers = {}
    self.mouseReleaseEventObservers = {}

  def setup(self):
    super(SliceTrackerTargetTablePlugin, self).setup()
    self.targetTable = qt.QTableView()
    self.targetTableModel = CustomTargetTableModel(self.logic)
    # self.targetTableModel.addEventObserver(vtk.vtkCommand.ModifiedEvent, self.updateNeedleModel)
    self.targetTable.setModel(self.targetTableModel)
    self.targetTable.setSelectionBehavior(qt.QTableView.SelectItems)
    self.setTargetTableSizeConstraints()
    self.targetTable.verticalHeader().hide()
    self.targetTable.minimumHeight = 150
    self.targetTable.setStyleSheet("QTableView::item:selected{background-color: #ff7f7f; color: black};")
    self.layout().addWidget(self.targetTable)

  def setTargetTableSizeConstraints(self):
    self.targetTable.horizontalHeader().setResizeMode(qt.QHeaderView.Stretch)
    self.targetTable.horizontalHeader().setResizeMode(0, qt.QHeaderView.Fixed)
    self.targetTable.horizontalHeader().setResizeMode(1, qt.QHeaderView.Stretch)
    self.targetTable.horizontalHeader().setResizeMode(2, qt.QHeaderView.ResizeToContents)
    self.targetTable.horizontalHeader().setResizeMode(3, qt.QHeaderView.ResizeToContents)

  def setupConnections(self):
    self.targetTable.connect('clicked(QModelIndex)', self.onTargetSelectionChanged)

  @onModuleSelected(SliceTrackerPlugin.MODULE_NAME)
  def onLayoutChanged(self, layout=None):
    self.disableTargetMovingMode()

  @vtk.calldata_type(vtk.VTK_STRING)
  def onCaseClosed(self, caller, event, callData):
    self.currentTargets = None

  def onActivation(self):
    super(SliceTrackerTargetTablePlugin, self).onActivation()
    self.moveTargetMode = False
    self.currentlyMovedTargetModelIndex = None
    self.connectKeyEventObservers()
    if self.currentTargets:
      self.onTargetSelectionChanged()

  def onDeactivation(self):
    super(SliceTrackerTargetTablePlugin, self).onDeactivation()
    self.disableTargetMovingMode()
    self.disconnectKeyEventObservers()

  def connectKeyEventObservers(self):
    interactors = [self.yellowSliceViewInteractor]
    if self.layoutManager.layout == constants.LAYOUT_FOUR_UP:
      interactors += [self.redSliceViewInteractor, self.greenSliceViewInteractor]
    for interactor in interactors:
      self.keyPressEventObservers[interactor] = interactor.AddObserver("KeyPressEvent", self.onKeyPressedEvent)
      self.keyReleaseEventObservers[interactor] = interactor.AddObserver("KeyReleaseEvent", self.onKeyReleasedEvent)

  def disconnectKeyEventObservers(self):
    for interactor, tag in self.keyPressEventObservers.iteritems():
      interactor.RemoveObserver(tag)
    for interactor, tag in self.keyReleaseEventObservers.iteritems():
      interactor.RemoveObserver(tag)

  def onKeyPressedEvent(self, caller, event):
    if not caller.GetKeySym() == 'd':
      return
    if not self.targetTableModel.computeCursorDistances:
      self.targetTableModel.computeCursorDistances = True
      self.calcCursorTargetsDistance()
      self.crosshairButton.addEventObserver(self.crosshairButton.CursorPositionModifiedEvent,
                                            self.calcCursorTargetsDistance)

  def onKeyReleasedEvent(self, caller, event):
    if not caller.GetKeySym() == 'd':
      return
    self.targetTableModel.computeCursorDistances = False
    self.crosshairButton.removeEventObserver(self.crosshairButton.CursorPositionModifiedEvent,
                                             self.calcCursorTargetsDistance)

  @vtk.calldata_type(vtk.VTK_OBJECT)
  def calcCursorTargetsDistance(self, caller, event, callData):
    if not self.targetTableModel.computeCursorDistances:
      return
    ras = xyz = [0.0, 0.0, 0.0]
    insideView = callData.GetCursorPositionRAS(ras)
    sliceNode = callData.GetCursorPositionXYZ(xyz)

    if not insideView or sliceNode not in [self.redSliceNode, self.yellowSliceNode, self.greenSliceNode]:
      self.targetTableModel.cursorPosition = None
      return
    self.targetTableModel.cursorPosition = ras

  def onTargetSelectionChanged(self, modelIndex=None):
    # onCurrentResultSelected event
    if not modelIndex:
      self.getAndSelectTargetFromTable()
      return
    if self.moveTargetMode is True and modelIndex != self.currentlyMovedTargetModelIndex:
      self.disableTargetMovingMode()
    self.lastSelectedModelIndex = modelIndex
    if not self.currentTargets:
      self.currentTargets = self.session.data.initialTargets
    self.jumpSliceNodesToNthTarget(modelIndex.row())
    # self.updateNeedleModel()
    self.targetTableModel.currentTargetIndex = self.lastSelectedModelIndex.row()
    self.updateSelection(self.lastSelectedModelIndex.row())

  def updateSelection(self, row):
    self.targetTable.clearSelection()
    first = self.targetTable.model().index(row, 0)
    second = self.targetTable.model().index(row, 1)

    selection = qt.QItemSelection(first, second)
    self.targetTable.selectionModel().select(selection, qt.QItemSelectionModel.Select)

  def jumpSliceNodesToNthTarget(self, targetIndex):
    currentTargetsSliceNodes = []
    if self.layoutManager.layout in [constants.LAYOUT_RED_SLICE_ONLY, constants.LAYOUT_SIDE_BY_SIDE]:
      targets = self.session.data.initialTargets
      if self.session.currentSeries and self.session.seriesTypeManager.isVibe(self.session.currentSeries):
        targets = self.targetTableModel.targetList
      self.jumpSliceNodeToTarget(self.redSliceNode, targets, targetIndex)
      self.logic.setTargetSelected(targets, selected=False)
      targets.SetNthFiducialSelected(targetIndex, True)

    if self.layoutManager.layout == constants.LAYOUT_SIDE_BY_SIDE:
      currentTargetsSliceNodes = [self.yellowSliceNode]
    elif self.layoutManager.layout == constants.LAYOUT_FOUR_UP:
      currentTargetsSliceNodes = [self.redSliceNode, self.yellowSliceNode, self.greenSliceNode]

    for sliceNode in currentTargetsSliceNodes:
      self.jumpSliceNodeToTarget(sliceNode, self.currentTargets, targetIndex)
    self.logic.setTargetSelected(self.currentTargets, selected=False)
    self.currentTargets.SetNthFiducialSelected(targetIndex, True)

  def getAndSelectTargetFromTable(self):
    modelIndex = None
    if self.lastSelectedModelIndex:
      modelIndex = self.lastSelectedModelIndex
    else:
      if self.targetTableModel.rowCount():
        modelIndex = self.targetTableModel.index(0,0)
    if modelIndex:
      self.targetTable.clicked(modelIndex)

  def onMoveTargetRequest(self, modelIndex):
    if self.moveTargetMode:
      self.disableTargetMovingMode()
      if self.currentlyMovedTargetModelIndex != modelIndex:
        self.onMoveTargetRequest(modelIndex)
      self.currentlyMovedTargetModelIndex = None
    else:
      self.currentlyMovedTargetModelIndex = modelIndex
      self.enableTargetMovingMode()

  def enableTargetMovingMode(self):
    self.clearTargetMovementObserverAndAnnotations()
    targetName = self.targetTableModel.targetList.GetNthFiducialLabel(self.currentlyMovedTargetModelIndex.row())

    widgets = [self.yellowWidget] if self.layoutManager.layout == constants.LAYOUT_SIDE_BY_SIDE else \
                 [self.redWidget, self.yellowWidget, self.greenWidget]
    for widget in widgets:
      sliceView = widget.sliceView()
      interactor = sliceView.interactorStyle().GetInteractor()
      observer = interactor.AddObserver(vtk.vtkCommand.LeftButtonReleaseEvent, self.onViewerClickEvent)
      sliceView.setCursor(qt.Qt.CrossCursor)
      annotation = SliceAnnotation(widget, "Target Movement Mode (%s)" % targetName, opacity=0.5,
                                   verticalAlign="top", horizontalAlign="center")
      self.mouseReleaseEventObservers[widget] = (observer, annotation)
    self.moveTargetMode = True

  def disableTargetMovingMode(self):
    self.clearTargetMovementObserverAndAnnotations()
    self.mouseReleaseEventObservers = {}
    self.moveTargetMode = False

  def clearTargetMovementObserverAndAnnotations(self):
    for widget, (observer, annotation) in self.mouseReleaseEventObservers.iteritems():
      sliceView = widget.sliceView()
      interactor = sliceView.interactorStyle().GetInteractor()
      interactor.RemoveObserver(observer)
      sliceView.setCursor(qt.Qt.ArrowCursor)
      annotation.remove()

  def onViewerClickEvent(self, observee=None, event=None):
    posXY = observee.GetEventPosition()
    widget = self.getWidgetForInteractor(observee)
    posRAS = self.xyToRAS(widget.sliceLogic(), posXY)
    if self.currentlyMovedTargetModelIndex is not None:
      self.currentResult.targets.isGoingToBeMoved(self.targetTableModel.targetList,
                                                  self.currentlyMovedTargetModelIndex.row())
      self.targetTableModel.targetList.SetNthFiducialPositionFromArray(self.currentlyMovedTargetModelIndex.row(),
                                                                       posRAS)
    self.disableTargetMovingMode()

  def getWidgetForInteractor(self, observee):
    for widget in self.mouseReleaseEventObservers.keys():
      sliceView = widget.sliceView()
      interactor = sliceView.interactorStyle().GetInteractor()
      if interactor is observee:
        return widget
    return None

  # def updateNeedleModel(self, caller=None, event=None):
  #   if self.showNeedlePathButton.checked and self.logic.zFrameRegistrationSuccessful:
  #     modelIndex = self.lastSelectedModelIndex
  #     try:
  #       start, end = self.targetTableModel.currentGuidanceComputation.needleStartEndPositions[modelIndex.row()]
  #       self.logic.createNeedleModelNode(start, end)
  #     except KeyError:
  #       self.logic.removeNeedleModelNode()

