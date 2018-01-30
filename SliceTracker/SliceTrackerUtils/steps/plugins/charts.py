import vtk
import qt
import ctk
import ast
import slicer
import logging


from ..base import SliceTrackerPlugin, SliceTrackerLogicBase
from ...session import SliceTrackerSession
from ...sessionData import RegistrationResult


class SliceTrackerDisplacementChartLogic(SliceTrackerLogicBase):

  def __init__(self):
    super(SliceTrackerDisplacementChartLogic, self).__init__()
    self.session = SliceTrackerSession()

  def calculateTargetDisplacement(self, prevTargets, currTargets, targetIndex):
    prevPos = [0.0, 0.0, 0.0]
    currPos = [0.0, 0.0, 0.0]
    currTargets.GetNthFiducialPosition(targetIndex, currPos)
    prevTargets.GetNthFiducialPosition(targetIndex, prevPos)
    displacement = [currPos[0] - prevPos[0], currPos[1] - prevPos[1], currPos[2] - prevPos[2]]
    return displacement


class SliceTrackerDisplacementChartPlugin(SliceTrackerPlugin):

  ShowEvent = vtk.vtkCommand.UserEvent + 561
  HideEvent = vtk.vtkCommand.UserEvent + 562

  NAME = "DisplacementChart"
  LogicClass = SliceTrackerDisplacementChartLogic

  PlotColorLR = qt.QColor(213, 94, 0)
  PlotColorPA = qt.QColor(0, 114, 178)
  PlotColorIS = qt.QColor(204, 121, 167)
  PlotColor3D = qt.QColor(0, 0, 0)

  def __init__(self):
    super(SliceTrackerDisplacementChartPlugin, self).__init__()
    self.session = SliceTrackerSession()
    self.session.addEventObserver(self.session.TargetSelectionEvent, self.onTargetSelectionChanged)

  def resetChart(self):
    for arr in [self.arrX, self.arrXD, self.arrYD, self.arrZD, self.arrD]:
      arr.Initialize()

  def setup(self):
    super(SliceTrackerDisplacementChartPlugin, self).setup()

    self.plotViewNode = None
    self.plotChartNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLPlotChartNode")
    self.plotChartNode.SetAttribute('XAxisLabelName', 'Series Number')
    self.plotChartNode.SetAttribute('YAxisLabelName', 'Displacement')

    self.setupChartTable()
    self.initializePlotWidget()

    self.collapsibleButton = ctk.ctkCollapsibleButton()
    self.collapsibleButton.text = "Plotting"
    self.collapsibleButton.collapsed = 0
    self.collapsibleButton.setLayout(qt.QGridLayout())

    self.collapsibleButton.layout().addWidget(self.plotWidget)
    self.layout().addWidget(self.collapsibleButton)
    self.plotWidget.show()

  def setupChartTable(self):
    self.chartTable = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLTableNode", "Target Displacement")

    self.arrX = self.createFloatArray('X Axis')
    self.arrXD = self.createFloatArray('L/R Displacement')
    self.arrYD = self.createFloatArray('P/A Displacement')
    self.arrZD = self.createFloatArray('I/S Displacement')
    self.arrD = self.createFloatArray('3-D Distance')

    for a in [self.arrX, self.arrXD,  self.arrYD, self.arrZD, self.arrD]:
      self.chartTable.AddColumn(a)

  def createFloatArray(self, name):
    floatArray = vtk.vtkFloatArray()
    floatArray.SetName(name)
    return floatArray

  def initializePlotWidget(self):
    layoutManager = slicer.app.layoutManager()
    if layoutManager.plotWidget(0) is not None:
      self.plotWidget = layoutManager.plotWidget(0)
    else:
      self.plotWidget = slicer.qMRMLPlotWidget()
      self.plotWidget.setColorLogic(slicer.modules.colors.logic())
      self.plotWidget.setMRMLScene(slicer.mrmlScene)
    self.updatePlotNode()

  def initializeChart(self, coverProstateSeriesNumber):
    self.arrX.InsertNextValue(coverProstateSeriesNumber)
    for arr in [self.arrXD, self.arrYD, self.arrZD, self.arrD]:
      arr.InsertNextValue(0)

  def addPlotPoints(self, displacement, seriesNumber):
    numCurrentRows = self.chartTable.GetNumberOfRows()
    self.plotChartNode.RemoveAllPlotDataNodeIDs()
    for i in range(len(displacement)):
      if numCurrentRows == 0:
        self.initializeChart(self.session.data.getMostRecentApprovedCoverProstateRegistration().seriesNumber)
      self.arrX.InsertNextValue(seriesNumber)
      for component, arr in enumerate([self.arrXD, self.arrYD, self.arrZD]):
        arr.InsertNextValue(displacement[i][component])
      distance = (displacement[i][0] ** 2 + displacement[i][1] ** 2 + displacement[i][2] ** 2) ** 0.5
      self.arrD.InsertNextValue(distance)

    for index, plot in enumerate([self.PlotColorLR, self.PlotColorPA, self.PlotColorIS, self.PlotColor3D], start=1):
      self.createPlot(plot, index)

  def updatePlotNode(self):
    if self.plotWidget.mrmlPlotViewNode() is None:
      self.plotViewNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLPlotViewNode")
      self.plotWidget.setMRMLPlotViewNode(self.plotViewNode)
    self.plotViewNode = self.plotWidget.mrmlPlotViewNode()
    self.plotViewNode.SetPlotChartNodeID(self.plotChartNode.GetID())

  def getPlotWidget(self):
    return self.plotWidget

  def createPlot(self, color, plotNumber):
    plotDataNode = slicer.mrmlScene.AddNode(slicer.vtkMRMLPlotDataNode())
    plotDataNode.SetName(self.chartTable.GetColumnName(plotNumber))
    plotDataNode.SetAndObserveTableNodeID(self.chartTable.GetID())
    plotDataNode.SetXColumnName(self.chartTable.GetColumnName(0))
    plotDataNode.SetYColumnName(self.chartTable.GetColumnName(plotNumber))
    plotDataNode.SetPlotColor([color.red(), color.green(), color.blue(), color.alpha()])
    plotDataNode.SetMarkerStyle(4)
    plotDataNode.SetMarkerSize(3 * plotDataNode.GetLineWidth())

    self.plotChartNode.AddAndObservePlotDataNodeID(plotDataNode.GetID())

  def updateTargetDisplacementChart(self, targetsAvailable):
    if self.isTargetDisplacementChartDisplayable(self.session.currentSeries) and targetsAvailable:
      self.resetChart()
      results = sorted([r for r in self.session.data.registrationResults.values() if r.approved],
                       key=lambda r: r.seriesNumber)
      if not self.session.currentResult.wasEvaluated():
        results.append(self.session.currentResult)
      for currIndex, currResult in enumerate(results[1:], 1):
        prevTargets = results[currIndex-1].targets.approved
        if not self.session.currentResult.wasEvaluated() and currIndex == len(results[1:]):
          currTargets = self.currResultTargets
        else:
          currTargets = currResult.targets.approved
        displacement = self.logic.calculateTargetDisplacement(prevTargets, currTargets, self.targetIndex)
        self.invokeEvent(self.ShowEvent)
        self.addPlotPoints([displacement], currResult.seriesNumber)
      self.invokeEvent(self.ShowEvent)
    else:
      self.invokeEvent(self.HideEvent)

  def isTargetDisplacementChartDisplayable(self, selectedSeries):
    if not selectedSeries or not (self.session.seriesTypeManager.isCoverProstate(selectedSeries) or
                                  self.session.seriesTypeManager.isGuidance(selectedSeries)) or \
                                  self.session.data.registrationResultWasRejected(selectedSeries):
      return False
    selectedSeriesNumber = RegistrationResult.getSeriesNumberFromString(selectedSeries)
    approvedResults = sorted([r for r in self.session.data.registrationResults.values() if r.approved],
                             key=lambda r: r.seriesNumber)
    nonSelectedApprovedResults = filter(lambda x: x.seriesNumber != selectedSeriesNumber, approvedResults)
    if len(nonSelectedApprovedResults) == 0 or self.session.currentResult is None:
      return False
    return True

  @vtk.calldata_type(vtk.VTK_STRING)
  def onTargetSelectionChanged(self, caller, event, callData):
    info = ast.literal_eval(callData)
    targetsAvailable = info['nodeId'] and info['index'] != -1
    if targetsAvailable:
      self.targetIndex = info['index']
      self.currResultTargets = slicer.mrmlScene.GetNodeByID(info['nodeId'])
      logging.debug(info)
    self.updateTargetDisplacementChart(targetsAvailable)