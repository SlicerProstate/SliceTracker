import numpy
import ctk
import qt
import vtk
import slicer
import logging
from ...constants import SliceTrackerConstants as constants
from SlicerProstateUtils.decorators import logmethod
from ..base import SliceTrackerPlugin, SliceTrackerLogicBase

from SlicerProstateUtils.helpers import SliceAnnotation


class SliceTrackerRegistrationResultsLogic(SliceTrackerLogicBase):

  def __init__(self):
    super(SliceTrackerRegistrationResultsLogic, self).__init__()

  def cleanup(self):
    pass


class SliceTrackerRegistrationResultsPlugin(SliceTrackerPlugin):

  LogicClass = SliceTrackerRegistrationResultsLogic

  @property
  def resultSelectorVisible(self):
    return self.resultSelector.visible

  @resultSelectorVisible.setter
  def resultSelectorVisible(self, visible):
    self.resultSelector.visible = visible

  @property
  def registrationTypeButtonsVisible(self):
    return self.registrationTypesGroupBox.visible

  @registrationTypeButtonsVisible.setter
  def registrationTypeButtonsVisible(self, visible):
    self.registrationTypesGroupBox.visible = visible

  @property
  def visualEffectsVisible(self):
    return self.visualEffectsGroupBox.visible

  @visualEffectsVisible.setter
  def visualEffectsVisible(self, visible):
    self.visualEffectsGroupBox.visible = visible

  @property
  def titleVisible(self):
    return self.registrationResultsGroupBox.title == self._title

  @titleVisible.setter
  def titleVisible(self, visible):
    self.registrationResultsGroupBox.title = self._title if visible else ""

  _title = "Registration Results"

  def __init__(self):
    super(SliceTrackerRegistrationResultsPlugin, self).__init__()

  def setupIcons(self):
    self.revealCursorIcon = self.createIcon('icon-revealCursor.png')

  def setup(self):
    self.registrationResultsGroupBox = qt.QGroupBox("Registration Results")
    self.registrationResultsGroupBoxLayout = qt.QGridLayout()
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
    self.layout().addWidget(self.registrationResultsGroupBox)


  def setRegistrationResultButtonVisibility(self, show):
    self.registrationButtonGroup.visible = show

  def setupVisualEffectsUIElements(self):
    self.setupOpacity()
    self.setupRock()
    self.setupFlicker()

    self.animaHolderLayout = self.createHLayout([self.rockCheckBox, self.flickerCheckBox])
    self.visualEffectsGroupBox = qt.QGroupBox("Visual Effects")
    self.visualEffectsGroupBoxLayout = qt.QFormLayout(self.visualEffectsGroupBox)
    self.revealCursorButton = self.createButton("", icon=self.revealCursorIcon, checkable=True,
                                                toolTip="Use reveal cursor")
    slider = self.createHLayout([self.opacitySpinBox, self.animaHolderLayout])
    self.visualEffectsGroupBoxLayout.addWidget(self.createVLayout([slider, self.revealCursorButton]))

  def setupOpacity(self):
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

  def setupRock(self):
    self.rockCount = 0
    self.rockTimer = self.createTimer(50, self.onRockToggled, singleShot=False)
    self.rockCheckBox = qt.QCheckBox("Rock")
    self.rockCheckBox.checked = False

  def setupFlicker(self):
    self.flickerTimer = self.createTimer(400, self.onFlickerToggled, singleShot=False)
    self.flickerCheckBox = qt.QCheckBox("Flicker")
    self.flickerCheckBox.checked = False

  def setupConnections(self):
    self.registrationButtonGroup.connect('buttonClicked(QAbstractButton*)', self.onRegistrationButtonChecked)
    self.resultSelector.connect('currentIndexChanged(QString)', self.onRegistrationResultSelected)
    self.revealCursorButton.connect('toggled(bool)', self.onRevealToggled)
    self.rockCheckBox.connect('toggled(bool)', self.onRockToggled)
    self.flickerCheckBox.connect('toggled(bool)', self.onFlickerToggled)
    self.opacitySpinBox.valueChanged.connect(self.onOpacitySpinBoxChanged)
    self.opacitySlider.valueChanged.connect(self.onOpacitySliderChanged)

  def onLayoutChanged(self):
    if not self.currentResult:
      return
    self.setupRegistrationResultView()
    self.onRegistrationResultSelected(self.currentResult.name)
    self.onOpacitySpinBoxChanged(self.opacitySpinBox.value)
    self.setFiducialNodeVisibility(self.session.data.initialTargets,
                                   show=self.layoutManager.layout != constants.LAYOUT_FOUR_UP)

  def show(self):
    qt.QWidget.show(self)
    self.onActivation()

  def hide(self):
    qt.QWidget.hide(self)
    self.onDeactivation()

  @logmethod(logging.INFO)
  def onActivation(self):
    if not self.currentResult:
      return
    self.updateRegistrationResultSelector()
    defaultLayout = self.getSetting("DEFAULT_EVALUATION_LAYOUT")
    self.setupRegistrationResultView(layout=getattr(constants, defaultLayout, constants.LAYOUT_SIDE_BY_SIDE))

  def onDeactivation(self):
    # TODO cleanup scene from the data used here
    self.removeSliceAnnotations()
    self.resetVisualEffects()

  def onRegistrationButtonChecked(self, button):
    # self.disableTargetMovingMode()
    if getattr(self.currentResult.targets, button.name) is None:
      return self.bSplineResultButton.click()
    self.displayRegistrationResultsByType(button.name)

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

  def onFlickerToggled(self):
    self.updateRevealCursorAvailability()
    if self.flickerCheckBox.checked:
      self.startFlickering()
    else:
      self.stopFlickering()

  def onRevealToggled(self, checked):
    self.revealCursor = getattr(self, "revealCursor", None)
    if self.revealCursor:
      self.revealCursor.tearDown()
    if checked:
      import CompareVolumes
      self.revealCursor = CompareVolumes.LayerReveal()

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
      self.onRegistrationButtonChecked(self.registrationButtonGroup.checkedButton())
    else:
      self.bSplineResultButton.click()

  def startRocking(self):
    if self.flickerCheckBox.checked:
      self.flickerCheckBox.checked = False
    self.rockTimer.start()
    self.opacitySpinBox.value = 0.5 + numpy.sin(self.rockCount / 10.) / 2.
    self.rockCount += 1

  def stopRocking(self):
    self.rockTimer.stop()
    self.opacitySpinBox.value = 1.0

  def startFlickering(self):
    if self.rockCheckBox.checked:
      self.rockCheckBox.checked = False
    self.flickerTimer.start()
    self.opacitySpinBox.value = 1.0 if self.opacitySpinBox.value == 0.0 else 0.0

  def stopFlickering(self):
    self.flickerTimer.stop()
    self.opacitySpinBox.value = 1.0

  def resetVisualEffects(self):
    self.flickerCheckBox.checked = False
    self.rockCheckBox.checked = False
    self.revealCursorButton.checked = False

  def setOldNewIndicatorAnnotationOpacity(self, value):
    self.registrationResultNewImageAnnotation = getattr(self, "registrationResultNewImageAnnotation", None)
    if self.registrationResultNewImageAnnotation:
      self.registrationResultNewImageAnnotation.opacity = value

    self.registrationResultOldImageAnnotation = getattr(self, "registrationResultOldImageAnnotation", None)
    if self.registrationResultOldImageAnnotation:
      self.registrationResultOldImageAnnotation.opacity = 1.0 - value

  def updateRevealCursorAvailability(self):
    self.revealCursorButton.checked = False
    self.revealCursorButton.enabled = not (self.rockCheckBox.checked or self.flickerCheckBox.checked)

  def updateRegistrationResultSelector(self):
    self.resultSelector.clear()
    for result in reversed(self.session.data.getResultsBySeriesNumber(self.currentResult.seriesNumber)):
      self.resultSelector.addItem(result.name)
    self.resultSelector.visible = self.resultSelector.model().rowCount() > 1

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
