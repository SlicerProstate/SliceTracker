import os
import qt
import slicer
from base import SliceTrackerLogicBase, SliceTrackerStep
from plugins.results import SliceTrackerRegistrationResultsPlugin
from ..constants import SliceTrackerConstants as constants


class SliceTrackerEvaluationStepLogic(SliceTrackerLogicBase):

  def __init__(self):
    super(SliceTrackerEvaluationStepLogic, self).__init__()

  def cleanup(self):
    pass


class SliceTrackerEvaluationStep(SliceTrackerStep):

  NAME = "Evaluation"
  LogicClass = SliceTrackerEvaluationStepLogic

  def __init__(self):
    self.modulePath = os.path.dirname(slicer.util.modulePath(self.MODULE_NAME)).replace(".py", "")
    super(SliceTrackerEvaluationStep, self).__init__()
    self.keyPressEventObservers = {}
    self.keyReleaseEventObservers = {}

  def setup(self):
    self.setupIcons()
    self.registrationEvaluationGroupBox = qt.QGroupBox()
    self.registrationEvaluationGroupBoxLayout = qt.QGridLayout()
    self.registrationEvaluationGroupBox.setLayout(self.registrationEvaluationGroupBoxLayout)

    self.setupTargetsTable()
    self.setupRegistrationValidationButtons()

    self.regResultsPlugin = SliceTrackerRegistrationResultsPlugin()
    self.addPlugin(self.regResultsPlugin)

    self.registrationEvaluationGroupBoxLayout.addWidget(self.regResultsPlugin, 3, 0)
    self.registrationEvaluationGroupBoxLayout.addWidget(self.targetTable, 4, 0)  # factor out the table since it is used in both Overview and evaluation step
    self.registrationEvaluationGroupBoxLayout.addWidget(self.registrationEvaluationButtonsGroupBox, 5, 0)
    self.registrationEvaluationGroupBoxLayout.setRowStretch(6, 1)
    self.layout().addWidget(self.registrationEvaluationGroupBox)

  def setupRegistrationValidationButtons(self):
    self.approveRegistrationResultButton = self.createButton("Approve", toolTip="Approve")
    self.retryRegistrationButton = self.createButton("Retry", toolTip="Retry")
    self.rejectRegistrationResultButton = self.createButton("Reject", toolTip="Reject")
    self.registrationEvaluationButtonsGroupBox = self.createHLayout([self.retryRegistrationButton,
                                                                     self.approveRegistrationResultButton,
                                                                     self.rejectRegistrationResultButton])

  def setupTargetsTable(self):
    self.targetTable = qt.QTableView()
    self.targetTable.setSelectionBehavior(qt.QTableView.SelectItems)
    self.setTargetTableSizeConstraints()
    self.targetTable.verticalHeader().hide()
    self.targetTable.minimumHeight = 150
    self.targetTable.setStyleSheet("QTableView::item:selected{background-color: #ff7f7f; color: black};")

  def setTargetTableSizeConstraints(self):
    self.targetTable.horizontalHeader().setResizeMode(qt.QHeaderView.Stretch)
    self.targetTable.horizontalHeader().setResizeMode(0, qt.QHeaderView.Fixed)
    self.targetTable.horizontalHeader().setResizeMode(1, qt.QHeaderView.Stretch)
    self.targetTable.horizontalHeader().setResizeMode(2, qt.QHeaderView.ResizeToContents)
    self.targetTable.horizontalHeader().setResizeMode(3, qt.QHeaderView.ResizeToContents)

  def setupConnections(self):

    self.retryRegistrationButton.clicked.connect(self.onRetryRegistrationButtonClicked)
    self.approveRegistrationResultButton.clicked.connect(self.onApproveRegistrationResultButtonClicked)
    self.rejectRegistrationResultButton.clicked.connect(self.onRejectRegistrationResultButtonClicked)
    # self.registrationDetailsButton.clicked.connect(self.onShowRegistrationDetails)

  def setupSessionObservers(self):
    super(SliceTrackerEvaluationStep, self).setupSessionObservers()
    self.session.addEventObserver(self.session.InitiateEvaluationEvent, self.onInitiateEvaluation)

  def removeSessionEventObservers(self):
    super(SliceTrackerEvaluationStep, self).removeSessionEventObservers()
    self.session.removeEventObserver(self.session.InitiateEvaluationEvent, self.onInitiateEvaluation)

  def onRetryRegistrationButtonClicked(self):
    self.session.retryRegistration()

  def onApproveRegistrationResultButtonClicked(self):
    results = self.session.data.getResultsBySeriesNumber(self.currentResult.seriesNumber)
    for result in [r for r in results if r is not self.currentResult]:
      result.reject()
    self.currentResult.approve(registrationType=self.regResultsPlugin.registrationButtonGroup.checkedButton().name)
    # if self.ratingWindow.isRatingEnabled():
    #   self.ratingWindow.show(disableWidget=self.parent)

  def onRejectRegistrationResultButtonClicked(self):
    results = self.session.data.getResultsBySeriesNumber(self.currentResult.seriesNumber)
    for result in [r for r in results if r is not self.currentResult]:
      result.reject()
    self.currentResult.reject()

  def onLayoutChanged(self):
    # self.disableTargetMovingMode()
    pass

  def onInitiateEvaluation(self, caller, event):
    self.active = True

  def onActivation(self):
    super(SliceTrackerEvaluationStep, self).onActivation()
    # self.redOnlyLayoutButton.enabled = False
    # self.sideBySideLayoutButton.enabled = True
    # self.registrationEvaluationGroupBoxLayout.addWidget(self.targetTable, 4, 0)
    self.rejectRegistrationResultButton.enabled = not self.getSetting("COVER_PROSTATE") in self.currentResult.name
    self.currentResult.save(self.session.outputDirectory)
    self.currentResult.printSummary()
    # self.targetTable.connect('doubleClicked(QModelIndex)', self.onMoveTargetRequest)

    self.connectKeyEventObservers()
    if not self.logic.isVolumeExtentValid(self.currentResult.volumes.bSpline):
      slicer.util.infoDisplay(
        "One or more empty volume were created during registration process. You have three options:\n"
        "1. Reject the registration result \n"
        "2. Retry with creating a new segmentation \n"
        "3. Set targets to your preferred position (in Four-Up layout)",
        title="Action needed: Registration created empty volume(s)", windowTitle="SliceTracker")

  def onDeactivation(self):
    super(SliceTrackerEvaluationStep, self).onDeactivation()
    self.hideAllLabels()
    self.hideAllFiducialNodes()

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
    # TODO
    pass
    # if not caller.GetKeySym() == 'd':
    #   return
    # if not self.targetTableModel.computeCursorDistances:
    #   self.targetTableModel.computeCursorDistances = True
    #   # self.calcCursorTargetsDistance()
    #   self.crosshairButton.addEventObserver(self.crosshairButton.CursorPositionModifiedEvent,
    #                                         self.calcCursorTargetsDistance)

  def onKeyReleasedEvent(self, caller, event):
    # TODO
    pass
    # if not caller.GetKeySym() == 'd':
    #   return
    # self.targetTableModel.computeCursorDistances = False
    # self.crosshairButton.removeEventObserver(self.crosshairButton.CursorPositionModifiedEvent,
    #                                          self.calcCursorTargetsDistance)