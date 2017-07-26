import vtk
import qt
import ctk
import ast


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

  def setup(self):
    super(SliceTrackerDisplacementChartPlugin, self).setup()
    self._chartView = ctk.ctkVTKChartView()
    self._chartView.minimumSize = qt.QSize(200, 200)
    self.isTargets = False
    self._showLegend = False
    self.xAxis.SetTitle('Series Number')
    self.yAxis.SetTitle('Displacement')
    self.chartTable = vtk.vtkTable()

    self.arrX = vtk.vtkFloatArray()
    self.arrX.SetName('X Axis')

    self.arrXD = vtk.vtkFloatArray()
    self.arrXD.SetName('L/R Displacement')

    self.arrYD = vtk.vtkFloatArray()
    self.arrYD.SetName('P/A Displacement')

    self.arrZD = vtk.vtkFloatArray()
    self.arrZD.SetName('I/S Displacement')

    self.arrD = vtk.vtkFloatArray()
    self.arrD.SetName('3-D Distance')

    self.chartTable.AddColumn(self.arrX)
    self.chartTable.AddColumn(self.arrXD)
    self.chartTable.AddColumn(self.arrYD)
    self.chartTable.AddColumn(self.arrZD)
    self.chartTable.AddColumn(self.arrD)

    self.chartPopupWindow = None
    self.chartPopupSize = qt.QSize(600, 300)
    self.chartPopupPosition = qt.QPoint(0, 0)

    self.showLegendCheckBox = qt.QCheckBox('Show legend')
    self.showLegendCheckBox.setChecked(0)

    self.dispChartCollapsibleButton = ctk.ctkCollapsibleButton()
    self.dispChartCollapsibleButton.text = "Plotting"
    self.dispChartCollapsibleButton.collapsed = 0
    plotFrameLayout = qt.QGridLayout(self.dispChartCollapsibleButton)
    self.plottingFrameWidget = qt.QWidget()
    self.plottingFrameLayout = qt.QGridLayout()
    self.plottingFrameWidget.setLayout(self.plottingFrameLayout)
    self.plottingFrameLayout.addWidget(self.showLegendCheckBox, 0, 0)
    self.plottingFrameLayout.addWidget(self._chartView, 1, 0)

    self.popupChartButton = qt.QPushButton("Undock chart")
    self.popupChartButton.setCheckable(True)
    self.plottingFrameLayout.addWidget(self.popupChartButton, 2, 0)
    plotFrameLayout.addWidget(self.plottingFrameWidget)
    self.layout().addWidget(self.dispChartCollapsibleButton)

  def setupConnections(self):
    self.popupChartButton.connect('toggled(bool)', self.onDockChartViewToggled)
    self.showLegendCheckBox.connect('stateChanged(int)', self.onShowLegendChanged)

  def addPlotPoints(self, triplets, seriesNumber):
    numCurrentRows = self.chartTable.GetNumberOfRows()
    self.chartView.removeAllPlots()
    for i in range(0, len(triplets)):
      if numCurrentRows == 0:
        self.arrX.InsertNextValue(seriesNumber - 1)
        self.arrXD.InsertNextValue(0)
        self.arrYD.InsertNextValue(0)
        self.arrZD.InsertNextValue(0)
        self.arrD.InsertNextValue(0)
        self._chartView.show()
        if not self.showLegendCheckBox.isVisible():
          self.showLegendCheckBox.show()
      self.arrX.InsertNextValue(seriesNumber)
      self.arrXD.InsertNextValue(triplets[i][0])
      self.arrYD.InsertNextValue(triplets[i][1])
      self.arrZD.InsertNextValue(triplets[i][2])
      distance = (triplets[i][0] ** 2 + triplets[i][1] ** 2 + triplets[i][2] ** 2) ** 0.5
      self.arrD.InsertNextValue(distance)

    xvals = vtk.vtkDoubleArray()
    xlabels = vtk.vtkStringArray()
    maxXIndex = self.arrX.GetNumberOfValues()
    for j in range(0, maxXIndex):
      xvals.InsertNextValue(self.arrX.GetValue(j))
      xlabels.InsertNextValue(str(int(self.arrX.GetValue(j))))
    self.xAxis.SetCustomTickPositions(xvals, xlabels)
    self.xAxis.SetBehavior(vtk.vtkAxis.FIXED)
    self.xAxis.SetRange(self.arrX.GetValue(0), self.arrX.GetValue(maxXIndex - 1) + 0.1)

    plot = self.chart.AddPlot(vtk.vtkChart.LINE)
    plot.SetInputData(self.chartTable, 0, 1)
    plot.SetColor(255, 0, 0, 255)
    vtk.vtkPlotLine.SafeDownCast(plot).SetMarkerStyle(4)
    vtk.vtkPlotLine.SafeDownCast(plot).SetMarkerSize(3 * plot.GetPen().GetWidth())

    plot2 = self.chart.AddPlot(vtk.vtkChart.LINE)
    plot2.SetInputData(self.chartTable, 0, 2)
    plot2.SetColor(0, 255, 0, 255)
    vtk.vtkPlotLine.SafeDownCast(plot2).SetMarkerStyle(4)
    vtk.vtkPlotLine.SafeDownCast(plot2).SetMarkerSize(3 * plot2.GetPen().GetWidth())

    plot3 = self.chart.AddPlot(vtk.vtkChart.LINE)
    plot3.SetInputData(self.chartTable, 0, 3)
    plot3.SetColor(0, 0, 255, 255)
    vtk.vtkPlotLine.SafeDownCast(plot3).SetMarkerStyle(4)
    vtk.vtkPlotLine.SafeDownCast(plot3).SetMarkerSize(3 * plot3.GetPen().GetWidth())

    plot4 = self.chart.AddPlot(vtk.vtkChart.LINE)
    plot4.SetInputData(self.chartTable, 0, 4)
    plot4.SetColor(0, 0, 0, 255)
    vtk.vtkPlotLine.SafeDownCast(plot4).SetMarkerStyle(4)
    vtk.vtkPlotLine.SafeDownCast(plot4).SetMarkerSize(3 * plot4.GetPen().GetWidth())

  def resetChart(self):
    self.arrX.Initialize()
    self.arrXD.Initialize()
    self.arrYD.Initialize()
    self.arrZD.Initialize()
    self.arrD.Initialize()
    if self.showLegendCheckBox.isChecked() and not self._chartView.isVisible():
      self.showLegendCheckBox.setChecked(False)

  def updateTargetDisplacementChart(self):
    if self.isTargetDisplacementChartDisplayable(self.session.currentSeries) and self.isTargets:
      self.resetChart()
      results = sorted(self.session.data.getResultsAsList(), key=lambda s: s.seriesNumber)
      prevIndex = 0
      for currIndex, currResult in enumerate(results[1:], 1):
        if results[prevIndex].approved and currResult.approved:
          prevTargets = results[prevIndex].targets.approved
          currTargets = currResult.targets.approved
          displacement = self.logic.calculateTargetDisplacement(prevTargets, currTargets, self.targetIndex)
          self.addPlotPoints([displacement], currResult.seriesNumber)
          prevIndex = currIndex
        elif currResult.approved:
          prevIndex = currIndex
        else:
          prevIndex += 1
      self.invokeEvent(self.ShowEvent)
    else:
      self.invokeEvent(self.HideEvent)
      if self.chartPopupWindow.isVisible():
        self.chartPopupWindow.close()
        self.dockChartView()

  def isTargetDisplacementChartDisplayable(self, selectedSeries):
    if selectedSeries is None:
      return
    selectedSeriesNumber = RegistrationResult.getSeriesNumberFromString(selectedSeries)
    approvedResults = sorted([r for r in self.session.data.registrationResults.values() if r.approved], key=lambda r: r.seriesNumber)
    nonSelectedApprovedResults = filter(lambda x: x.seriesNumber != selectedSeriesNumber, approvedResults)
    if len(nonSelectedApprovedResults) == 0:
      return False
    return True

  def onShowLegendChanged(self, checked):
    self.chart.SetShowLegend(True if checked == 2 else False)
    self.chartView.scene().SetDirty(True)

  @vtk.calldata_type(vtk.VTK_STRING)
  def onTargetSelectionChanged(self, caller, event, callData):
    info = ast.literal_eval(callData)
    if not info['nodeId'] or info['index'] == -1:
      self.isTargets = False
    else:
      self.targetIndex = info['index']
      self.isTargets = True
      print "%s" % info
    self.updateTargetDisplacementChart()

  def onDockChartViewToggled(self, checked):
    if checked:
      self.chartPopupWindow = qt.QDialog()
      self.chartPopupWindow.setWindowFlags(qt.Qt.WindowStaysOnTopHint)
      layout = qt.QGridLayout()
      self.chartPopupWindow.setLayout(layout)
      layout.addWidget(self.showLegendCheckBox, 0, 0)
      layout.addWidget(self._chartView, 1, 0)
      self.chartPopupWindow.finished.connect(self.dockChartView)
      self.chartPopupWindow.resize(self.chartPopupSize)
      self.chartPopupWindow.move(self.chartPopupPosition)
      self.chartPopupWindow.show()
      self.popupChartButton.hide()
    else:
      self.chartPopupWindow.close()

  def dockChartView(self):
    self.chartPopupSize = self.chartPopupWindow.size
    self.chartPopupPosition = self.chartPopupWindow.pos
    self.plottingFrameLayout.addWidget(self.showLegendCheckBox, 0, 0)
    self.plottingFrameLayout.addWidget(self._chartView, 1, 0)
    self.plottingFrameLayout.addWidget(self.popupChartButton, 2, 0)
    self.popupChartButton.blockSignals(True)
    self.popupChartButton.checked = False
    self.popupChartButton.show()
    self.popupChartButton.blockSignals(False)