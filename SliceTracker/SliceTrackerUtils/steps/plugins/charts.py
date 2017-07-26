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

  PlotColorLR = qt.QColor('red')
  PlotColorPA = qt.QColor('yellowgreen')
  PlotColorIS = qt.QColor('lightblue')
  PlotColor3D = qt.QColor('black')

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

  def initializeChart(self, seriesNumber):
    self.arrX.InsertNextValue(seriesNumber - 1)
    for arr in [self.arrXD, self.arrYD, self.arrZD, self.arrD]:
      arr.InsertNextValue(0)

  def addPlotPoints(self, displacement, seriesNumber):
    numCurrentRows = self.chartTable.GetNumberOfRows()
    self.chartView.removeAllPlots()
    for i in range(len(displacement)):
      if numCurrentRows == 0:
        self.initializeChart(seriesNumber)
      self.arrX.InsertNextValue(seriesNumber)
      for component, arr in enumerate([self.arrXD, self.arrYD, self.arrZD]):
        arr.InsertNextValue(displacement[i][component])
      distance = (displacement[i][0] ** 2 + displacement[i][1] ** 2 + displacement[i][2] ** 2) ** 0.5
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

    self.createPlot(self.PlotColorLR, 1)
    self.createPlot(self.PlotColorPA, 2)
    self.createPlot(self.PlotColorIS, 3)
    self.createPlot(self.PlotColor3D, 4)

  def createPlot(self, color, plotNumber):
    plot = self.chart.AddPlot(vtk.vtkChart.LINE)
    plot.SetInputData(self.chartTable, 0, plotNumber)
    plot.SetColor(color.red(), color.blue(), color.green(), color.alpha())
    vtk.vtkPlotLine.SafeDownCast(plot).SetMarkerStyle(4)
    vtk.vtkPlotLine.SafeDownCast(plot).SetMarkerSize(3 * plot.GetPen().GetWidth())

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