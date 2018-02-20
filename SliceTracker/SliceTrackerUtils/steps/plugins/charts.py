import vtk
import qt
import ctk
import ast
import slicer
import logging


from ..base import SliceTrackerPlugin, SliceTrackerLogicBase
from ...session import SliceTrackerSession
from ...sessionData import RegistrationResult
from ...constants import SliceTrackerConstants as constants

from SlicerDevelopmentToolboxUtils.decorators import onModuleSelected


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

  PlotColorLR = [213/255.0, 94/255.0, 0]
  PlotColorPA = [0, 114/255.0, 178/255.0]
  PlotColorIS = [204/255.0, 121/255.0, 167/255.0]
  PlotColor3D = [0, 0, 0]
  PlotNames = ["L/R Displaement","P/A Displacement", "I/S Displacement", "3-D Distance"]

  def __init__(self):
    super(SliceTrackerDisplacementChartPlugin, self).__init__()
    self.session = SliceTrackerSession()
    self.session.addEventObserver(self.session.TargetSelectionEvent, self.onTargetSelectionChanged)

  def resetChart(self):
    for arr in [self.arrX, self.arrXD, self.arrYD, self.arrZD, self.arrD]:
      arr.Initialize()

  def setup(self):
    super(SliceTrackerDisplacementChartPlugin, self).setup()

    self.plotView = None
    self.plotWidget = None
    self.plotViewNode = None
    self.plotWidgetViewNode = None
    self.plotSeriesNodes = []

    self.plotChartNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLPlotChartNode")
    self.plotChartNode.SetXAxisTitle('Series Number')
    self.plotChartNode.SetYAxisTitle('Displacement')

    self.setupChartTable()
    self.initializePlotWidgets()

    self.showLegendCheckBox = qt.QCheckBox('Show legend')
    self.showLegendCheckBox.setChecked(1)
    self.showLegendCheckBox.connect('stateChanged(int)', self.onShowLegendChanged)

    self.collapsibleButton = ctk.ctkCollapsibleButton()
    self.collapsibleButton.text = "Plotting"
    self.collapsibleButton.collapsed = 0
    self.collapsibleButton.setLayout(qt.QGridLayout())

    self.collapsibleButton.layout().addWidget(self.showLegendCheckBox, 0, 0)
    self.collapsibleButton.layout().addWidget(self.plotView, 1, 0)
    self.layout().addWidget(self.collapsibleButton)
    self.plotView.show()

  def setupChartTable(self):
    self.chartTable = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLTableNode", "Target Displacement")

    self.arrX = self.createFloatArray('X Axis')
    self.arrXD = self.createFloatArray('L/R Displ')
    self.arrYD = self.createFloatArray('P/A Displ')
    self.arrZD = self.createFloatArray('I/S Displ')
    self.arrD = self.createFloatArray('3-D Dis')

    for a in [self.arrX, self.arrXD,  self.arrYD, self.arrZD, self.arrD]:
      self.chartTable.AddColumn(a)

  def createFloatArray(self, name):
    floatArray = vtk.vtkFloatArray()
    floatArray.SetName(name)
    return floatArray

  def initializePlotWidgets(self):
    if self.plotView is None:
      self.plotView = slicer.qMRMLPlotView()
      self.plotView.setMRMLScene(slicer.mrmlScene)
      self.plotView.setMinimumSize(400,200)
    layoutManager = slicer.app.layoutManager()
    layout = layoutManager.layout
    if layout == constants.LAYOUT_FOUR_UP_QUANTITATIVE:
      self.plotWidget = layoutManager.plotWidget(0) if layoutManager.plotWidget(0).isVisible() else layoutManager.plotWidget(1)
    if self.plotWidget or self.plotView:
      self.updatePlotViewNodes()

  def initializeChart(self, coverProstateSeriesNumber):
    self.arrX.InsertNextValue(coverProstateSeriesNumber)
    for arr in [self.arrXD, self.arrYD, self.arrZD, self.arrD]:
      arr.InsertNextValue(0)

  def addPlotPoints(self, displacement, seriesNumber):
    numCurrentRows = self.chartTable.GetNumberOfRows()
    if self.plotChartNode is None:
      self.initializePlotChartNode()
      self.plotViewNode.SetPlotChartNodeID(self.plotChartNode.GetID())

    for i in range(len(displacement)):
      if numCurrentRows == 0:
        self.initializeChart(self.session.data.getMostRecentApprovedCoverProstateRegistration().seriesNumber)
      self.arrX.InsertNextValue(seriesNumber)
      for component, arr in enumerate([self.arrXD, self.arrYD, self.arrZD]):
        arr.InsertNextValue(displacement[i][component])
      distance = (displacement[i][0] ** 2 + displacement[i][1] ** 2 + displacement[i][2] ** 2) ** 0.5
      self.arrD.InsertNextValue(distance)
    if self.plotChartNode.GetNumberOfPlotSeriesNodes() == 0:
      for index, plot in enumerate([self.PlotColorLR, self.PlotColorPA, self.PlotColorIS, self.PlotColor3D], start=1):
        self.createPlot(plot, index)
    else:
      self.plotChartNode.RemoveAllPlotSeriesNodeIDs()
      for plotSeriesNode in self.plotSeriesNodes:
        self.plotChartNode.AddAndObservePlotSeriesNodeID(plotSeriesNode.GetID())

  def updatePlotViewNodes(self):
    if self.plotViewNode is None:
        self.plotViewNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLPlotViewNode")
        self.plotView.setMRMLPlotViewNode(self.plotViewNode)
        self.plotViewNode.SetPlotChartNodeID(self.plotChartNode.GetID())
    elif self.plotWidget is not None:
      self.plotWidgetViewNode = self.plotWidget.mrmlPlotViewNode()
      self.plotWidgetViewNode.SetPlotChartNodeID(self.plotChartNode.GetID())

  def createPlot(self, color, plotNumber):
    plotSeriesNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLPlotSeriesNode", self.PlotNames[plotNumber-1])
    plotSeriesNode.SetAndObserveTableNodeID(self.chartTable.GetID())
    plotSeriesNode.SetXColumnName(self.chartTable.GetColumnName(0))
    plotSeriesNode.SetYColumnName(self.chartTable.GetColumnName(plotNumber))
    plotSeriesNode.SetColor(color)
    plotSeriesNode.SetPlotType(slicer.vtkMRMLPlotSeriesNode.PlotTypeScatter)
    plotSeriesNode.SetMarkerStyle(4)
    plotSeriesNode.SetMarkerSize(3 * plotSeriesNode.GetLineWidth())

    self.plotSeriesNodes.append(plotSeriesNode)
    self.plotChartNode.AddAndObservePlotSeriesNodeID(plotSeriesNode.GetID())

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

  def onShowLegendChanged(self, checked):
    self.plotChartNode.SetLegendVisibility(True if checked == 2 else False)

  @vtk.calldata_type(vtk.VTK_STRING)
  def onTargetSelectionChanged(self, caller, event, callData):
    info = ast.literal_eval(callData)
    targetsAvailable = info['nodeId'] and info['index'] != -1
    if targetsAvailable:
      self.targetIndex = info['index']
      self.currResultTargets = slicer.mrmlScene.GetNodeByID(info['nodeId'])
      logging.debug(info)
    self.updateTargetDisplacementChart(targetsAvailable)

  @onModuleSelected(SliceTrackerPlugin.MODULE_NAME)
  def onLayoutChanged(self, layout=None):
    if layout == constants.LAYOUT_FOUR_UP_QUANTITATIVE:
      self.collapsibleButton.hide()
      self.initializePlotWidgets()

  def onDeactivation(self):
    slicer.mrmlScene.RemoveNode(self.plotWidgetViewNode)
    slicer.mrmlScene.RemoveNode(self.plotViewNode)
    self.plotWidget = None
    self.plotView = None
