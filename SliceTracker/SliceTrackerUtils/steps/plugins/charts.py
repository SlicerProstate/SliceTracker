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

  @property
  def chartView(self):
    return self._chartView

  @property
  def chart(self):
    return self._chartView.chart()

  @property
  def xAxis(self):
    return self.chart.GetAxis(1)

  @property
  def yAxis(self):
    return self.chart.GetAxis(0)

  @property
  def showLegend(self):
    self._showLegend = getattr(self, "_showLegend", False)
    return self._showLegend

  @showLegend.setter
  def showLegend(self, value):
    assert type(value) is bool, "Only boolean values are allowed for this class member"
    self._showLegend = value
    self.chart.SetShowLegend(value)

  def __init__(self):
    super(SliceTrackerDisplacementChartPlugin, self).__init__()
    self.session = SliceTrackerSession()
    self.session.addEventObserver(self.session.TargetSelectionEvent, self.onTargetSelectionChanged)

  def resetChart(self):
    for arr in [self.arrX, self.arrXD, self.arrYD, self.arrZD, self.arrD]:
      arr.Initialize()
    if self.showLegendCheckBox.isChecked() and not self._chartView.isVisible():
      self.showLegendCheckBox.setChecked(False)

  def setup(self):
    super(SliceTrackerDisplacementChartPlugin, self).setup()
    self._chartView = ctk.ctkVTKChartView()
    self._chartView.minimumSize = qt.QSize(200, 200)
    self.xAxis.SetTitle('Series Number')
    self.yAxis.SetTitle('Displacement')

    self.setupChartTable()
    self.setupPopupWindow()

    self.showLegendCheckBox = qt.QCheckBox('Show legend')
    self.showLegendCheckBox.setChecked(0)

    self.undockChartButton = self.createButton("Undock chart")

    self.collapsibleButton = ctk.ctkCollapsibleButton()
    self.collapsibleButton.text = "Plotting"
    self.collapsibleButton.collapsed = 0
    self.collapsibleButton.setLayout(qt.QGridLayout())

    self.plottingFrameWidget = qt.QWidget()
    self.plottingFrameWidget.setLayout(qt.QGridLayout())
    self.plottingFrameWidget.layout().addWidget(self.showLegendCheckBox, 0, 0)
    self.plottingFrameWidget.layout().addWidget(self._chartView, 1, 0)
    self.plottingFrameWidget.layout().addWidget(self.undockChartButton, 2, 0)

    self.collapsibleButton.layout().addWidget(self.plottingFrameWidget)

    self.layout().addWidget(self.collapsibleButton)

  def setupPopupWindow(self):
    self.chartPopupWindow = None
    self.chartPopupSize = qt.QSize(600, 300)
    self.chartPopupPosition = qt.QPoint(0, 0)

  def setupChartTable(self):
    self.chartTable = vtk.vtkTable()

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

  def setupConnections(self):
    self.undockChartButton.clicked.connect(self.onDockChartViewClicked)
    self.showLegendCheckBox.connect('stateChanged(int)', self.onShowLegendChanged)

  def initializeChart(self, coverProstateSeriesNumber):
    self.arrX.InsertNextValue(coverProstateSeriesNumber)
    for arr in [self.arrXD, self.arrYD, self.arrZD, self.arrD]:
      arr.InsertNextValue(0)

  def addPlotPoints(self, displacement, seriesNumber):
    numCurrentRows = self.chartTable.GetNumberOfRows()
    self.chartView.removeAllPlots()
    for i in range(len(displacement)):
      if numCurrentRows == 0:
        self.initializeChart(self.session.data.getMostRecentApprovedCoverProstateRegistration().seriesNumber)
      self.arrX.InsertNextValue(seriesNumber)
      for component, arr in enumerate([self.arrXD, self.arrYD, self.arrZD]):
        arr.InsertNextValue(displacement[i][component])
      distance = (displacement[i][0] ** 2 + displacement[i][1] ** 2 + displacement[i][2] ** 2) ** 0.5
      self.arrD.InsertNextValue(distance)

    self.configureChartXAxis()
    for index, plot in enumerate([self.PlotColorLR, self.PlotColorPA, self.PlotColorIS, self.PlotColor3D], start=1):
      self.createPlot(plot, index)

  def configureChartXAxis(self):
    xVals = vtk.vtkDoubleArray()
    xLabels = vtk.vtkStringArray()
    maxXIndex = self.arrX.GetNumberOfValues()
    for j in range(0, maxXIndex):
      xVals.InsertNextValue(self.arrX.GetValue(j))
      xLabels.InsertNextValue(str(int(self.arrX.GetValue(j))))
    self.xAxis.SetCustomTickPositions(xVals, xLabels)
    self.xAxis.SetBehavior(vtk.vtkAxis.FIXED)
    self.xAxis.SetRange(self.arrX.GetValue(0), self.arrX.GetValue(maxXIndex - 1) + 0.1)

  def createPlot(self, color, plotNumber):
    plot = self.chart.AddPlot(vtk.vtkChart.LINE)
    plot.SetInputData(self.chartTable, 0, plotNumber)
    plot.SetColor(color.red(), color.blue(), color.green(), color.alpha())
    vtk.vtkPlotLine.SafeDownCast(plot).SetMarkerStyle(4)
    vtk.vtkPlotLine.SafeDownCast(plot).SetMarkerSize(3 * plot.GetPen().GetWidth())

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
        self.addPlotPoints([displacement], currResult.seriesNumber)
      self.invokeEvent(self.ShowEvent)
    else:
      self.invokeEvent(self.HideEvent)
      if self.chartPopupWindow and self.chartPopupWindow.isVisible():
        self.chartPopupWindow.close()
        self.dockChartView()

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
    self.chart.SetShowLegend(True if checked == 2 else False)
    self.chartView.scene().SetDirty(True)

  @vtk.calldata_type(vtk.VTK_STRING)
  def onTargetSelectionChanged(self, caller, event, callData):
    info = ast.literal_eval(callData)
    targetsAvailable = info['nodeId'] and info['index'] != -1
    if targetsAvailable:
      self.targetIndex = info['index']
      self.currResultTargets = slicer.mrmlScene.GetNodeByID(info['nodeId'])
      logging.debug(info)
    self.updateTargetDisplacementChart(targetsAvailable)

  def onDockChartViewClicked(self):
    self.chartPopupWindow = qt.QDialog()
    self.chartPopupWindow.setWindowTitle("Target Displacement Chart")
    self.chartPopupWindow.setWindowFlags(qt.Qt.WindowStaysOnTopHint)
    self.chartPopupWindow.setLayout(qt.QGridLayout())
    self.chartPopupWindow.layout().addWidget(self.plottingFrameWidget)
    self.chartPopupWindow.finished.connect(self.dockChartView)
    self.chartPopupWindow.resize(self.chartPopupSize)
    self.chartPopupWindow.move(self.chartPopupPosition)
    self.chartPopupWindow.show()
    self.undockChartButton.hide()
    self.invokeEvent(self.HideEvent)

  def dockChartView(self):
    self.chartPopupSize = self.chartPopupWindow.size
    self.chartPopupPosition = self.chartPopupWindow.pos

    self.collapsibleButton.layout().addWidget(self.plottingFrameWidget)
    self.plottingFrameWidget.show()
    self.undockChartButton.show()
    self.invokeEvent(self.ShowEvent)

  def onDeactivation(self):
    super(SliceTrackerDisplacementChartPlugin, self).onDeactivation()
    if self.chartPopupWindow and self.chartPopupWindow.isVisible():
      self.chartPopupWindow.close()
      self.dockChartView()