import os, ast, shutil
import qt, vtk, ctk, slicer

from ...constants import SliceTrackerConstants
from ..base import SliceTrackerStep

from SlicerProstateUtils.helpers import SampleDataDownloader
from SlicerProstateUtils.decorators import *


class SliceTrackerTrainingPlugin(SliceTrackerStep):

  NAME = "Training"

  def __init__(self):
    self.modulePath = os.path.dirname(slicer.util.modulePath(self.MODULE_NAME)).replace(".py", "")
    super(SliceTrackerTrainingPlugin, self).__init__()
    self.sampleDownloader = SampleDataDownloader(True)
    self.setupSessionObservers()

  def setup(self):
    self.collapsibleTrainingArea = ctk.ctkCollapsibleButton()
    self.collapsibleTrainingArea.collapsed = True
    self.collapsibleTrainingArea.text = "Training"

    self.simulatePreopPhaseButton = self.createButton("Simulate preop phase", enabled=False)
    self.simulateIntraopPhaseButton = self.createButton("Simulate intraop phase", enabled=False)

    self.trainingsAreaLayout = qt.QGridLayout(self.collapsibleTrainingArea)
    self.trainingsAreaLayout.addWidget(self.createHLayout([self.simulatePreopPhaseButton,
                                                           self.simulateIntraopPhaseButton]))
    self.layout().addWidget(self.collapsibleTrainingArea)

  def setupConnections(self):
    self.simulatePreopPhaseButton.clicked.connect(self.startPreopPhaseSimulation)
    self.simulateIntraopPhaseButton.clicked.connect(self.startIntraopPhaseSimulation)

  def startPreopPhaseSimulation(self):
    self.session.trainingMode = True
    if self.session.preopDICOMReceiver.dicomReceiver.isRunning():
      self.session.preopDICOMReceiver.dicomReceiver.stopStoreSCP()
    self.simulatePreopPhaseButton.enabled = False
    preopZipFile = self.initiateSampleDataDownload(SliceTrackerConstants.PREOP_SAMPLE_DATA_URL)
    if not self.sampleDownloader.wasCanceled and preopZipFile:
      self.unzipFileAndCopyToDirectory(preopZipFile, self.session.preopDICOMDirectory)

  def startIntraopPhaseSimulation(self):
    self.simulateIntraopPhaseButton.enabled = False
    intraopZipFile = self.initiateSampleDataDownload(SliceTrackerConstants.INTRAOP_SAMPLE_DATA_URL)
    if not self.sampleDownloader.wasCanceled and intraopZipFile:
      self.unzipFileAndCopyToDirectory(intraopZipFile, self.session.intraopDICOMDirectory)

  def initiateSampleDataDownload(self, url):
    filename = os.path.basename(url)
    self.sampleDownloader.resetAndInitialize()
    self.sampleDownloader.addEventObserver(self.sampleDownloader.EVENTS['status_changed'], self.onDownloadProgressUpdated)
    # self.customStatusProgressBar.show()
    downloadedFile = self.sampleDownloader.downloadFileIntoCache(url, filename)
    # self.customStatusProgressBar.hide()
    return None if self.sampleDownloader.wasCanceled else downloadedFile

  @onReturnProcessEvents
  @vtk.calldata_type(vtk.VTK_STRING)
  def onDownloadProgressUpdated(self, caller, event, callData):
    message, percent = ast.literal_eval(callData)
    logging.info("%s, %s" %(message, percent))
    # self.customStatusProgressBar.updateStatus(message, percent)

  def unzipFileAndCopyToDirectory(self, filepath, copyToDirectory):
    import zipfile
    try:
      zip_ref = zipfile.ZipFile(filepath, 'r')
      destination = filepath.replace(os.path.basename(filepath), "")
      logging.debug("extracting to %s " % destination)
      zip_ref.extractall(destination)
      zip_ref.close()
      self.copyDirectory(filepath.replace(".zip", ""), copyToDirectory)
    except zipfile.BadZipfile as exc:
      if self.preopTransferWindow:
        self.preopTransferWindow.hide()
      slicer.util.errorDisplay("An error appeared while extracting %s. If the file is corrupt, please delete it and try "
                               "again." % filepath, detailedText=str(exc.message))
      self.clearData()

  def copyDirectory(self, source, destination, recursive=True):
    print source
    assert os.path.isdir(source)
    for listObject in os.listdir(source):
      current = os.path.join(source, listObject)
      if os.path.isdir(current) and recursive:
        self.copyDirectory(current, destination, recursive)
      else:
        shutil.copy(current, destination)

  @logmethod(logging.INFO)
  def onNewCaseStarted(self, caller, event):
    self.simulatePreopPhaseButton.enabled = True

  def onIncomingDataSkipped(self, caller, event):
    self.simulatePreopPhaseButton.enabled = False
    self.simulateIntraopPhaseButton.enabled = True

  @logmethod(logging.INFO)
  def onCaseClosed(self, caller, event):
    self.simulatePreopPhaseButton.enabled = False
    self.simulateIntraopPhaseButton.enabled = False