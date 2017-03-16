import os
import numpy
import ctk
import qt
import slicer
from base import SliceTrackerStepLogic, SliceTrackerStep
from SliceTrackerUtils.constants import SliceTrackerConstants as constants
from SlicerProstateUtils.helpers import SliceAnnotation


class SliceTrackerEvaluationStepLogic(SliceTrackerStepLogic):

  def __init__(self):
    super(SliceTrackerEvaluationStepLogic, self).__init__()

  def cleanup(self):
    pass


class SliceTrackerEvaluationStep(SliceTrackerStep):

  NAME = "Evaluation"
  LogicClass = SliceTrackerEvaluationStepLogic

  @property
  def currentResult(self):
    return self.session.activeResult

  @currentResult.setter
  def currentResult(self, value):
    self.session.activeResult = value

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

    self.setupRegistrationResultsGroupBox()
    self.setupTargetsTable()
    self.setupRegistrationValidationButtons()
    self.registrationEvaluationGroupBoxLayout.addWidget(self.registrationResultsGroupBox, 3, 0)
    self.registrationEvaluationGroupBoxLayout.addWidget(self.targetTable, 4, 0)  # factor out the table since it is used in both Overview and evaluation step
    self.registrationEvaluationGroupBoxLayout.addWidget(self.registrationEvaluationButtonsGroupBox, 5, 0)
    self.registrationEvaluationGroupBoxLayout.setRowStretch(6, 1)
    self.layout().addWidget(self.registrationEvaluationGroupBox)

  def setupIcons(self):
    self.revealCursorIcon = self.createIcon('icon-revealCursor.png')

  def setupRegistrationValidationButtons(self):
    self.approveRegistrationResultButton = self.createButton("Approve", toolTip="Approve")
    self.retryRegistrationButton = self.createButton("Retry", toolTip="Retry")
    self.rejectRegistrationResultButton = self.createButton("Reject", toolTip="Reject")
    self.registrationEvaluationButtonsGroupBox = self.createHLayout([self.retryRegistrationButton,
                                                                     self.approveRegistrationResultButton,
                                                                     self.rejectRegistrationResultButton])

  def setupRegistrationResultsGroupBox(self):

    self.registrationResultsGroupBox = qt.QGroupBox("Registration Results")
    self.registrationResultsGroupBoxLayout = qt.QFormLayout()
    self.registrationResultsGroupBox.setLayout(self.registrationResultsGroupBoxLayout)

    self.resultSelector = ctk.ctkComboBox()
    self.registrationResultsGroupBoxLayout.addWidget(self.resultSelector)

    self.rigidResultButton = self.createButton('Rigid', checkable=True, name='rigid')
    self.affineResultButton = self.createButton('Affine', checkable=True, name='affine')
    self.bSplineResultButton = self.createButton('BSpline', checkable=True, name='bSpline')

    self.registrationButtonGroup = qt.QButtonGroup()
    self.registrationButtonGroup.addButton(self.rigidResultButton, 1)
    self.registrationButtonGroup.addButton(self.affineResultButton, 2)
    self.registrationButtonGroup.addButton(self.bSplineResultButton, 3)

    self.registrationTypesGroupBox = qt.QGroupBox("Type")
    self.registrationTypesGroupBoxLayout = qt.QFormLayout(self.registrationTypesGroupBox)
    self.registrationTypesGroupBoxLayout.addWidget(self.createVLayout([self.rigidResultButton,
                                                                       self.affineResultButton,
                                                                       self.bSplineResultButton]))
    self.setupVisualEffectsUIElements()

    self.registrationResultsGroupBoxLayout.addWidget(self.createHLayout([self.registrationTypesGroupBox,
                                                                         self.visualEffectsGroupBox]))

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

  def setupVisualEffectsUIElements(self):
    self.opacitySpinBox = qt.QDoubleSpinBox()
    self.opacitySpinBox.minimum = 0
    self.opacitySpinBox.maximum = 1.0
    self.opacitySpinBox.value = 0
    self.opacitySpinBox.singleStep = 0.05

    self.opacitySliderPopup = ctk.ctkPopupWidget(self.opacitySpinBox)
    popupLayout = qt.QHBoxLayout(self.opacitySliderPopup)
    self.opacitySlider = ctk.ctkDoubleSlider(self.opacitySliderPopup)
    self.opacitySlider.orientation = qt.Qt.Horizontal
    self.opacitySlider.minimum = 0
    self.opacitySlider.maximum = 1.0
    self.opacitySlider.value = 0
    self.opacitySlider.singleStep = 0.05

    popupLayout.addWidget(self.opacitySlider)
    self.opacitySliderPopup.verticalDirection = ctk.ctkBasePopupWidget.TopToBottom
    self.opacitySliderPopup.animationEffect = ctk.ctkBasePopupWidget.FadeEffect
    self.opacitySliderPopup.orientation = qt.Qt.Horizontal
    self.opacitySliderPopup.easingCurve = qt.QEasingCurve.OutQuart
    self.opacitySliderPopup.effectDuration = 100

    self.rockCount = 0
    self.rockTimer = qt.QTimer()
    self.rockTimer.setInterval(50)
    self.rockCheckBox = qt.QCheckBox("Rock")
    self.rockCheckBox.checked = False

    self.flickerTimer = qt.QTimer()
    self.flickerTimer.setInterval(400)
    self.flickerCheckBox = qt.QCheckBox("Flicker")
    self.flickerCheckBox.checked = False

    self.animaHolderLayout = self.createHLayout([self.rockCheckBox, self.flickerCheckBox])
    self.visualEffectsGroupBox = qt.QGroupBox("Visual Effects")
    self.visualEffectsGroupBoxLayout = qt.QFormLayout(self.visualEffectsGroupBox)
    self.revealCursorButton = self.createButton("", icon=self.revealCursorIcon, checkable=True,
                                                toolTip="Use reveal cursor")
    slider = self.createHLayout([self.opacitySpinBox, self.animaHolderLayout])
    self.visualEffectsGroupBoxLayout.addWidget(self.createVLayout([slider, self.revealCursorButton]))

  def setupConnections(self):
    self.resultSelector.connect('currentIndexChanged(QString)', self.onRegistrationResultSelected)
    self.registrationButtonGroup.connect('buttonClicked(int)', self.onRegistrationButtonChecked)

    self.retryRegistrationButton.clicked.connect(self.onRetryRegistrationButtonClicked)
    self.approveRegistrationResultButton.clicked.connect(self.onApproveRegistrationResultButtonClicked)
    self.rejectRegistrationResultButton.clicked.connect(self.onRejectRegistrationResultButtonClicked)
    # self.registrationDetailsButton.clicked.connect(self.onShowRegistrationDetails)

    self.revealCursorButton.connect('toggled(bool)', self.onRevealToggled)
    self.rockCheckBox.connect('toggled(bool)', self.onRockToggled)
    self.flickerCheckBox.connect('toggled(bool)', self.onFlickerToggled)

    self.opacitySpinBox.valueChanged.connect(self.onOpacitySpinBoxChanged)
    self.opacitySlider.valueChanged.connect(self.onOpacitySliderChanged)
    self.rockTimer.connect('timeout()', self.onRockToggled)
    self.flickerTimer.connect('timeout()', self.onFlickerToggled)

  def setupSessionObservers(self):
    super(SliceTrackerEvaluationStep, self).setupSessionObservers()
    self.session.addEventObserver(self.session.InitiateEvaluationEvent, self.onInitiateEvaluation)

  def removeSessionEventObservers(self):
    super(SliceTrackerEvaluationStep, self).removeSessionEventObservers()
    self.session.removeEventObserver(self.session.InitiateEvaluationEvent, self.onInitiateEvaluation)

  def onRetryRegistrationButtonClicked(self):
    self.removeSliceAnnotations()
    self.session.retryRegistration()

  def onApproveRegistrationResultButtonClicked(self):
    results = self.session.data.getResultsBySeriesNumber(self.currentResult.seriesNumber)
    for result in [r for r in results if r is not self.currentResult]:
      result.reject()
    self.currentResult.approve(registrationType=self.registrationButtonGroup.checkedButton().name)
    # if self.ratingWindow.isRatingEnabled():
    #   self.ratingWindow.show(disableWidget=self.parent)

  def onRejectRegistrationResultButtonClicked(self):
    results = self.session.data.getResultsBySeriesNumber(self.currentResult.seriesNumber)
    for result in [r for r in results if r is not self.currentResult]:
      result.reject()
    self.currentResult.reject()

  def onOpacitySpinBoxChanged(self, value):
    if self.opacitySlider.value != value:
      self.opacitySlider.value = value
    self.onOpacityChanged(value)

  def onOpacitySliderChanged(self, value):
    if self.opacitySpinBox.value != value:
      self.opacitySpinBox.value = value

  def onOpacityChanged(self, value):
    if self.layoutManager.layout == constants.LAYOUT_FOUR_UP:
      self.redCompositeNode.SetForegroundOpacity(value)
      self.greenCompositeNode.SetForegroundOpacity(value)
    self.yellowCompositeNode.SetForegroundOpacity(value)
    self.setOldNewIndicatorAnnotationOpacity(value)

  def onRockToggled(self):
    self.updateRevealCursorAvailability()
    if self.rockCheckBox.checked:
      self.startRocking()
    else:
      self.stopRocking()

  def startRocking(self):
    if self.flickerCheckBox.checked:
      self.flickerCheckBox.checked = False
    self.rockTimer.start()
    self.opacitySpinBox.value = 0.5 + numpy.sin(self.rockCount / 10.) / 2.
    self.rockCount += 1

  def stopRocking(self):
    self.rockTimer.stop()
    self.opacitySpinBox.value = 1.0

  def onFlickerToggled(self):
    self.updateRevealCursorAvailability()
    if self.flickerCheckBox.checked:
      self.startFlickering()
    else:
      self.stopFlickering()

  def startFlickering(self):
    if self.rockCheckBox.checked:
      self.rockCheckBox.checked = False
    self.flickerTimer.start()
    self.opacitySpinBox.value = 1.0 if self.opacitySpinBox.value == 0.0 else 0.0

  def stopFlickering(self):
    self.flickerTimer.stop()
    self.opacitySpinBox.value = 1.0

  def onRevealToggled(self, checked):
    self.revealCursor = getattr(self, "revealCursor", None)
    if self.revealCursor:
      self.revealCursor.tearDown()
    if checked:
      import CompareVolumes
      self.revealCursor = CompareVolumes.LayerReveal()

  def updateRevealCursorAvailability(self):
    self.revealCursorButton.checked = False
    self.revealCursorButton.enabled = not (self.rockCheckBox.checked or self.flickerCheckBox.checked)

  def resetVisualEffects(self):
    self.flickerCheckBox.checked = False
    self.rockCheckBox.checked = False
    self.revealCursorButton.checked = False

  def setOldNewIndicatorAnnotationOpacity(self, value):
    if self.registrationResultNewImageAnnotation:
      self.registrationResultNewImageAnnotation.opacity = value
    if self.registrationResultOldImageAnnotation:
      self.registrationResultOldImageAnnotation.opacity = 1.0 - value

  def onRegistrationButtonChecked(self, buttonId):
    # self.disableTargetMovingMode()
    if buttonId == 1:
      self.displayRegistrationResultsByType(registrationType="rigid")
    elif buttonId == 2:
      if not self.currentResult.targets.affine:
        return self.bSplineResultButton.click()
      self.displayRegistrationResultsByType(registrationType="affine")
    elif buttonId == 3:
      self.displayRegistrationResultsByType(registrationType="bSpline")

  def onLayoutChanged(self):
    # self.disableTargetMovingMode()
    self.setupRegistrationResultView()
    self.onRegistrationResultSelected(self.currentResult.name)
    self.onOpacitySpinBoxChanged(self.opacitySpinBox.value)
    # self.crosshairButton.checked = self.layoutManager.layout == constants.LAYOUT_FOUR_UP
    self.setFiducialNodeVisibility(self.session.data.initialTargets,
                                   show=self.layoutManager.layout != constants.LAYOUT_FOUR_UP)

  def onRegistrationResultSelected(self, seriesText, registrationType=None, showApproved=False):
    # self.disableTargetMovingMode()
    if not seriesText:
      return
    self.hideAllFiducialNodes()
    self.currentResult = seriesText
    self.affineResultButton.setEnabled(self.currentResult.targets.affine is not None)
    if registrationType:
      self.checkButtonByRegistrationType(registrationType)
    elif showApproved:
      self.displayApprovedRegistrationResults()
    elif self.registrationButtonGroup.checkedId() != -1:
      self.onRegistrationButtonChecked(self.registrationButtonGroup.checkedId())
    else:
      self.bSplineResultButton.click()

  def checkButtonByRegistrationType(self, registrationType):
    for button in self.registrationButtonGroup.buttons():
      if button.name == registrationType:
        button.click()
        break

  def displayApprovedRegistrationResults(self):
    self.displayRegistrationResults(self.currentResult.approvedTargets, self.currentResult.approvedRegistrationType)

  def displayRegistrationResultsByType(self, registrationType):
    self.displayRegistrationResults(self.currentResult.getTargets(registrationType), registrationType)

  def displayRegistrationResults(self, targets, registrationType):
    self.hideAllFiducialNodes()
    self.showCurrentTargets(targets)
    self.setupRegistrationResultSliceViews(registrationType)
    self.setPreopTargetVisibility()
    # self.selectLastSelectedTarget()

  def setPreopTargetVisibility(self):
    self.setFiducialNodeVisibility(self.session.data.initialTargets,
                                    show=self.layoutManager.layout == constants.LAYOUT_SIDE_BY_SIDE)

  def setupRegistrationResultSliceViews(self, registrationType):
    if self.layoutManager.layout in [constants.LAYOUT_SIDE_BY_SIDE, constants.LAYOUT_RED_SLICE_ONLY]:
      self.redCompositeNode.SetForegroundVolumeID(None)
      self.redCompositeNode.SetBackgroundVolumeID(self.session.data.initialVolume.GetID())
      compositeNodes = []

    if self.layoutManager.layout == constants.LAYOUT_SIDE_BY_SIDE:
      compositeNodes = [self.yellowCompositeNode]
    elif self.layoutManager.layout == constants.LAYOUT_FOUR_UP:
      compositeNodes = [self.redCompositeNode, self.yellowCompositeNode, self.greenCompositeNode]

    bgVolume = self.currentResult.getVolume(registrationType)
    bgVolume = bgVolume if bgVolume and self.logic.isVolumeExtentValid(bgVolume) else self.currentResult.volumes.fixed

    for compositeNode in compositeNodes:
      compositeNode.SetForegroundVolumeID(self.currentResult.volumes.fixed.GetID())
      compositeNode.SetBackgroundVolumeID(bgVolume.GetID())

    if self.layoutManager.layout == constants.LAYOUT_SIDE_BY_SIDE:
      self.setAxialOrientation()
    elif self.layoutManager.layout == constants.LAYOUT_FOUR_UP:
      self.setDefaultOrientation()
      self.setFiducialNodeVisibility(self.session.data.initialTargets, show=False)
    # self.centerViewsToProstate()

  def showCurrentTargets(self, targets):
    self.session.applyDefaultTargetDisplayNode(targets)
    self.setFiducialNodeVisibility(targets)

  def onInitiateEvaluation(self, caller, event):
    self.active = True

  def onActivation(self):
    # self.redOnlyLayoutButton.enabled = False
    # self.sideBySideLayoutButton.enabled = True
    # self.registrationEvaluationGroupBoxLayout.addWidget(self.targetTable, 4, 0)
    self.rejectRegistrationResultButton.enabled = not self.getSetting("COVER_PROSTATE") in self.currentResult.name

    self.currentResult.save(self.session.outputDirectory)
    # self.targetTable.connect('doubleClicked(QModelIndex)', self.onMoveTargetRequest)
    self.addNewTargetsToScene()

    self.updateRegistrationResultSelector()
    defaultLayout = self.getSetting("DEFAULT_EVALUATION_LAYOUT")
    self.setupRegistrationResultView(layout=getattr(constants, defaultLayout,
                                                    constants.LAYOUT_SIDE_BY_SIDE))

    self.currentResult.printSummary()
    self.connectKeyEventObservers()
    if not self.logic.isVolumeExtentValid(self.currentResult.volumes.bSpline):
      slicer.util.infoDisplay(
        "One or more empty volume were created during registration process. You have three options:\n"
        "1. Reject the registration result \n"
        "2. Retry with creating a new segmentation \n"
        "3. Set targets to your preferred position (in Four-Up layout)",
        title="Action needed: Registration created empty volume(s)", windowTitle="SliceTracker")

  def onDeactivation(self):
    self.removeSliceAnnotations()
    self.resetVisualEffects()
    self.hideAllLabels()
    self.hideAllFiducialNodes()

  def addNewTargetsToScene(self):
    for targetNode in self.getResultingTargets():
      slicer.mrmlScene.AddNode(targetNode)

  def setupRegistrationResultView(self, layout=None):
    # TODO: make a mixin or service from that
    if layout:
      self.layoutManager.setLayout(layout)
    self.hideAllLabels()
    self.addSliceAnnotationsBasedOnLayoutAndSetOrientation()
    self.refreshViewNodeIDs(self.session.data.initialTargets, [self.redSliceNode])
    self.setupViewNodesForCurrentTargets()

  def addSliceAnnotationsBasedOnLayoutAndSetOrientation(self):
    self.removeSliceAnnotations()
    if self.layoutManager.layout == constants.LAYOUT_FOUR_UP:
      self.addFourUpSliceAnnotations()
      self.setDefaultOrientation()
    else:
      self.addSideBySideSliceAnnotations()
      self.setAxialOrientation()

  def removeSliceAnnotations(self):
    self.sliceAnnotations = getattr(self, "sliceAnnotations", [])
    for annotation in self.sliceAnnotations:
      annotation.remove()
    self.sliceAnnotations = []
    for attr in ["registrationResultOldImageAnnotation", "registrationResultNewImageAnnotation"]:
      annotation = getattr(self, attr, None)
      if annotation:
        annotation.remove()
        setattr(self, attr, None)
    # self.clearTargetMovementObserverAndAnnotations()
    # self.removeMissingPreopDataAnnotation()

  def addSideBySideSliceAnnotations(self):
    self.sliceAnnotations.append(SliceAnnotation(self.redWidget, constants.LEFT_VIEWER_SLICE_ANNOTATION_TEXT,
                                                 fontSize=30, yPos=55))
    self.sliceAnnotations.append(SliceAnnotation(self.yellowWidget, constants.RIGHT_VIEWER_SLICE_ANNOTATION_TEXT,
                                                 yPos=55, fontSize=30))
    self.registrationResultNewImageAnnotation = SliceAnnotation(self.yellowWidget,
                                                                constants.RIGHT_VIEWER_SLICE_NEEDLE_IMAGE_ANNOTATION_TEXT,
                                                                yPos=35, opacity=0.0, color=(0,0.5,0))
    self.registrationResultOldImageAnnotation = SliceAnnotation(self.yellowWidget,
                                                                constants.RIGHT_VIEWER_SLICE_TRANSFORMED_ANNOTATION_TEXT,
                                                                yPos=35)
    self.registrationResultStatusAnnotation = None
    # self.onShowAnnotationsToggled(self.showAnnotationsButton.checked)

  def addFourUpSliceAnnotations(self):
    self.sliceAnnotations.append(SliceAnnotation(self.redWidget, constants.RIGHT_VIEWER_SLICE_ANNOTATION_TEXT, yPos=50,
                                                 fontSize=20))
    self.registrationResultNewImageAnnotation = SliceAnnotation(self.redWidget,
                                                                constants.RIGHT_VIEWER_SLICE_NEEDLE_IMAGE_ANNOTATION_TEXT,
                                                                yPos=35, opacity=0.0, color=(0,0.5,0), fontSize=15)
    self.registrationResultOldImageAnnotation = SliceAnnotation(self.redWidget,
                                                                constants.RIGHT_VIEWER_SLICE_TRANSFORMED_ANNOTATION_TEXT,
                                                                yPos=35, fontSize=15)
    self.registrationResultStatusAnnotation = None
    # TODO
    # self.onShowAnnotationsToggled(self.showAnnotationsButton.checked)

  def setupViewNodesForCurrentTargets(self):
    sliceNodes = [self.yellowSliceNode]
    if self.layoutManager.layout == constants.LAYOUT_FOUR_UP:
      sliceNodes = [self.redSliceNode, self.yellowSliceNode, self.greenSliceNode]
    for targetNode in self.getResultingTargets():
      self.refreshViewNodeIDs(targetNode, sliceNodes)
      targetNode.SetLocked(True)
    if self.currentResult.targets.approved:
      self.refreshViewNodeIDs(self.currentResult.targets.approved, sliceNodes)
      self.currentResult.targets.approved.SetLocked(True)

  def getResultingTargets(self):
    resultTargets = [self.currentResult.targets.rigid, self.currentResult.targets.affine,
                     self.currentResult.targets.bSpline]
    return [t for t in resultTargets if t is not None]

  def updateRegistrationResultSelector(self):
    self.resultSelector.clear()
    for result in reversed(self.session.data.getResultsBySeriesNumber(self.currentResult.seriesNumber)):
      self.resultSelector.addItem(result.name)
    self.resultSelector.visible = self.resultSelector.model().rowCount() > 1

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