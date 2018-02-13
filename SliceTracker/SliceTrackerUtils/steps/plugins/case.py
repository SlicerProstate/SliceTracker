import slicer
import os
import ctk
import vtk
import qt

from ...helpers import NewCaseSelectionNameWidget
from ..base import SliceTrackerPlugin, SliceTrackerLogicBase

from SlicerDevelopmentToolboxUtils.helpers import WatchBoxAttribute
from SlicerDevelopmentToolboxUtils.widgets import BasicInformationWatchBox
from SlicerDevelopmentToolboxUtils.icons import Icons
from SlicerDevelopmentToolboxUtils.mixins import ModuleLogicMixin


class SliceTrackerCaseManagerLogic(SliceTrackerLogicBase):

  def __init__(self):
    super(SliceTrackerCaseManagerLogic, self).__init__()


class SliceTrackerCaseManagerPlugin(SliceTrackerPlugin):

  LogicClass = SliceTrackerCaseManagerLogic
  NAME = "CaseManager"

  @property
  def caseRootDir(self):
    return self.casesRootDirectoryButton.directory

  @caseRootDir.setter
  def caseRootDir(self, path):
    try:
      exists = os.path.exists(path)
    except TypeError:
      exists = False
    self.setSetting('CasesRootLocation', path if exists else None)
    self.casesRootDirectoryButton.text = ModuleLogicMixin.truncatePath(path) if exists else "Choose output directory"
    self.casesRootDirectoryButton.toolTip = path
    self.openCaseButton.enabled = exists
    self.createNewCaseButton.enabled = exists

  def __init__(self):
    super(SliceTrackerCaseManagerPlugin, self).__init__()
    self.caseRootDir = self.getSetting('CasesRootLocation', self.MODULE_NAME)
    slicer.app.connect('aboutToQuit()', self.onSlicerQuits)

  def onSlicerQuits(self):
    if self.session.isRunning():
      self.onCloseCaseButtonClicked()

  def clearData(self):
    self.update()

  def setup(self):
    super(SliceTrackerCaseManagerPlugin, self).setup()
    iconSize = qt.QSize(36, 36)
    self.createNewCaseButton = self.createButton("", icon=Icons.new, iconSize=iconSize, toolTip="Start a new case")
    self.openCaseButton = self.createButton("", icon=Icons.open, iconSize=iconSize, toolTip="Open case")
    self.closeCaseButton = self.createButton("", icon=Icons.exit, iconSize=iconSize,
                                             toolTip="Close case with resume support", enabled=False)
    self.setupCaseWatchBox()
    self.casesRootDirectoryButton = self.createDirectoryButton(text="Choose cases root location",
                                                               caption="Choose cases root location",
                                                               directory=self.getSetting('CasesRootLocation',
                                                                                         self.MODULE_NAME))
    self.caseDirectoryInformationArea = ctk.ctkCollapsibleButton()
    self.caseDirectoryInformationArea.collapsed = True
    self.caseDirectoryInformationArea.text = "Directory Settings"
    self.directoryConfigurationLayout = qt.QGridLayout(self.caseDirectoryInformationArea)
    self.directoryConfigurationLayout.addWidget(qt.QLabel("Cases Root Directory"), 1, 0, 1, 1)
    self.directoryConfigurationLayout.addWidget(self.casesRootDirectoryButton, 1, 1, 1, 1)
    self.directoryConfigurationLayout.addWidget(self.caseWatchBox, 2, 0, 1, qt.QSizePolicy.ExpandFlag)

    self.caseGroupBox = qt.QGroupBox("Case")
    self.caseGroupBoxLayout = qt.QFormLayout(self.caseGroupBox)
    self.caseGroupBoxLayout.addWidget(self.createHLayout([self.createNewCaseButton, self.openCaseButton,
                                                          self.closeCaseButton]))
    self.caseGroupBoxLayout.addWidget(self.caseDirectoryInformationArea)
    self.layout().addWidget(self.caseGroupBox)

  def setupCaseWatchBox(self):
    watchBoxInformation = [WatchBoxAttribute('CurrentCaseDirectory', 'Directory'),
                           WatchBoxAttribute('CurrentPreopDICOMDirectory', 'Preop DICOM Directory: '),
                           WatchBoxAttribute('CurrentIntraopDICOMDirectory', 'Intraop DICOM Directory: '),
                           WatchBoxAttribute('mpReviewDirectory', 'mpReview Directory: ')]
    self.caseWatchBox = BasicInformationWatchBox(watchBoxInformation, title="Current Case")

  def setupConnections(self):
    self.createNewCaseButton.clicked.connect(self.onCreateNewCaseButtonClicked)
    self.openCaseButton.clicked.connect(self.onOpenCaseButtonClicked)
    self.closeCaseButton.clicked.connect(self.onCloseCaseButtonClicked)
    self.casesRootDirectoryButton.directoryChanged.connect(lambda: setattr(self, "caseRootDir",
                                                                           self.casesRootDirectoryButton.directory))

  def onCreateNewCaseButtonClicked(self):
    if not self.checkAndWarnUserIfCaseInProgress():
      return
    self.caseDialog = NewCaseSelectionNameWidget(self.caseRootDir)
    selectedButton = self.caseDialog.exec_()
    if selectedButton == qt.QMessageBox.Ok:
      self.session.createNewCase(self.caseDialog.newCaseDirectory)

  def onOpenCaseButtonClicked(self):
    if not self.checkAndWarnUserIfCaseInProgress():
      return
    self.session.directory = qt.QFileDialog.getExistingDirectory(self.parent().window(), "Select Case Directory",
                                                                 self.caseRootDir)

  def onCloseCaseButtonClicked(self):
    if not self.session.data.completed:
      dialog = qt.QMessageBox(qt.QMessageBox.Question, "SliceTracker", "Do you want to mark this case as completed?", qt.QMessageBox.Yes | qt.QMessageBox.No | qt.QMessageBox.Cancel, slicer.util.mainWindow(), qt.Qt.WindowStaysOnTopHint).exec_()
      if dialog == qt.QMessageBox.Yes:
        self.session.complete()
      elif dialog == qt.QMessageBox.Cancel:
        return
    if self.session.isRunning():
      self.session.close(save=False)

  def onNewCaseStarted(self, caller, event):
    self.update()

  def onCaseOpened(self, caller, event):
    self.update()

  def update(self):
    self.updateCaseButtons()
    self.updateCaseWatchBox()

  @vtk.calldata_type(vtk.VTK_STRING)
  def onCaseClosed(self, caller, event, callData):
    self.clearData()

  def onLoadingMetadataSuccessful(self, caller, event):
    self.updateCaseButtons()

  def updateCaseWatchBox(self):
    if not self.session.isRunning():
      self.caseWatchBox.reset()
      return
    self.caseWatchBox.setInformation("CurrentCaseDirectory", os.path.relpath(self.session.directory, self.caseRootDir),
                                     toolTip=self.session.directory)
    self.caseWatchBox.setInformation("CurrentPreopDICOMDirectory", os.path.relpath(self.session.preopDICOMDirectory,
                                                                                   self.caseRootDir),
                                     toolTip=self.session.preopDICOMDirectory)
    self.caseWatchBox.setInformation("CurrentIntraopDICOMDirectory", os.path.relpath(self.session.intraopDICOMDirectory,
                                                                                     self.caseRootDir),
                                     toolTip=self.session.intraopDICOMDirectory)
    self.caseWatchBox.setInformation("mpReviewDirectory", os.path.relpath(self.session.preprocessedDirectory,
                                                                          self.caseRootDir),
                                     toolTip=self.session.preprocessedDirectory)

  def updateCaseButtons(self):
    self.closeCaseButton.enabled = self.session.directory is not None

  def checkAndWarnUserIfCaseInProgress(self):
    if self.session.isRunning():
      if not slicer.util.confirmYesNoDisplay("Current case will be closed. Do you want to proceed?"):
        return False
    return True