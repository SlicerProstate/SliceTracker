import os
import unittest
from __main__ import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *

#
# RegistrationModule
#

class RegistrationModule(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "RegistrationModule" # TODO make this more human readable by adding spaces
    self.parent.categories = ["Examples"]
    self.parent.dependencies = []
    self.parent.contributors = ["Peter Behringer (SPL), Andriy Fedorov (SPL)"] # replace with "Firstname Lastname (Organization)"
    self.parent.helpText = """ Module for easy registration. """
    self.parent.acknowledgementText = """SPL, Brigham & Womens""" # replace with organization, grant and thanks.

#
# RegistrationModuleWidget
#

class RegistrationModuleWidget(ScriptedLoadableModuleWidget):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    # Parameters
    self.settings = qt.QSettings()
    self.temp = None

    # Create PushButtons for Workflow-Steps 1-4

    # Set Icon Size for the 4 Icon Items
    size=qt.QSize(130,130)

    # Create Data Selection Button
    pixmap=qt.QPixmap('/Users/peterbehringer/MyDevelopment/Icons/dunkel_rund_DATA.png')
    #pixmap=qt.QPixmap('/Users/peterbehringer/MyDevelopment/Icons/bright_rund_DATA.png')
    icon=qt.QIcon(pixmap)
    dataButton=qt.QPushButton()
    dataButton.setIcon(icon)
    dataButton.setIconSize(size)
    dataButton.setFixedHeight(140)
    dataButton.setFixedWidth(140)
    dataButton.setStyleSheet("background-color: rgb(48,48,48)")

    # Create Label Selection Button
    pixmap=qt.QPixmap('/Users/peterbehringer/MyDevelopment/Icons/dunkel_rund_LABEL.png')
    icon=qt.QIcon(pixmap)
    labelButton=qt.QPushButton()
    labelButton.setIcon(icon)
    labelButton.setIconSize(size)
    labelButton.setFixedHeight(140)
    labelButton.setFixedWidth(140)
    labelButton.setStyleSheet("background-color: rgb(48,48,48)")

    # Create Registration Button
    pixmap=qt.QPixmap('/Users/peterbehringer/MyDevelopment/Icons/dunkel_rund.png')
    icon=qt.QIcon(pixmap)
    regButton=qt.QPushButton()
    regButton.setIcon(icon)
    regButton.setIconSize(size)
    regButton.setFixedHeight(140)
    regButton.setFixedWidth(140)
    regButton.setStyleSheet("background-color: rgb(48,48,48)")

    # Create Data Selection Button
    pixmap=qt.QPixmap('/Users/peterbehringer/MyDevelopment/Icons/dunkel_rund_EVALUATIOn.png')
    icon=qt.QIcon(pixmap)
    evalButton=qt.QPushButton()
    evalButton.setIcon(icon)
    evalButton.setIconSize(size)
    evalButton.setFixedHeight(140)
    evalButton.setFixedWidth(140)
    evalButton.setStyleSheet("background-color: rgb(48,48,48)")

    # Create ButtonBox to put in Workstep Buttons
    buttonBox=qt.QDialogButtonBox()
    buttonBox.addButton(evalButton,buttonBox.ActionRole)
    buttonBox.addButton(regButton,buttonBox.ActionRole)
    buttonBox.addButton(labelButton,buttonBox.ActionRole)
    buttonBox.addButton(dataButton,buttonBox.ActionRole)
    buttonBox.setLayoutDirection(1)
    buttonBox.centerButtons=True
    self.layout.addWidget(buttonBox)

    # Set Layout
    lm=slicer.app.layoutManager()
    lm.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutSideBySideView)




    #
    # Step 1: Data Selection
    #




    # Create collapsible Button << Step 1: Data Selection >>
    dataSectionCollapsibleButton = ctk.ctkCollapsibleButton()
    dataSectionCollapsibleButton.text = "Step 1: Data Selection"
    self.layout.addWidget(dataSectionCollapsibleButton)

    # Layout within the collapsible Button section
    dataSectionFormLayout = qt.QFormLayout(dataSectionCollapsibleButton)

    # Layout within a row of that section
    selectPatientRowLayout = qt.QHBoxLayout()

    # Create PatientSelector
    patientSelector=ctk.ctkComboBox()
    selectPatientRowLayout.addWidget(patientSelector)
    dataSectionFormLayout.addRow("Select Patient: ", selectPatientRowLayout)

    # make all patient in dicom data base available
    # TODO: Update if database changed
    # Problem: Only available if preop data has DICOM format

    db = slicer.dicomDatabase

    patientNames = []
    patientIDs = []

    if db.patients()==None:
      patientSelector.addItem('None patient found')
    for patient in db.patients():
      for study in db.studiesForPatient(patient):
        for series in db.seriesForStudy(study):
          for file in db.filesForSeries(series):

             if db.fileValue(file,'0010,0010') not in patientNames:
               patientNames.append(db.fileValue(file,'0010,0010'))

             if db.fileValue(file,'0010,0020') not in patientIDs:
               patientIDs.append(db.fileValue(file,'0010,0020'))


    # add patientNames and patientIDs to patientSelector
    for patient in patientIDs:
     patientSelector.addItem(patient)

    # "load Preop Data" - Button
    self.loadPreopDataButton = qt.QPushButton("Load Preop Data")
    self.loadPreopDataButton.toolTip = "Load preprocedural data into Slicer"
    self.loadPreopDataButton.enabled = True

    # "Watch Directory" - Button
    self.watchIntraopCheckbox=qt.QCheckBox()
    self.watchIntraopCheckbox.toolTip = "Watch Directory"

    # Preop Directory Button
    self.preopDirButton = ctk.ctkDirectoryButton()
    self.preopDirButton.text = "Choose the preop data directory"
    dataSectionFormLayout.addRow("Preop directory selection:",self.preopDirButton)
    dataSectionFormLayout.addWidget(self.loadPreopDataButton)

    # Preop Directory Button
    self.intraopDirButton = ctk.ctkDirectoryButton()
    self.intraopDirButton.text = "Choose the intraop data directory"
    dataSectionFormLayout.addRow("Intraop directory selection:",self.intraopDirButton)
    dataSectionFormLayout.addRow("Watch Intraop Directory for new Data", self.watchIntraopCheckbox)

    # SERIES SELECTION
    self.step3frame = ctk.ctkCollapsibleGroupBox()
    self.step3frame.setTitle("Intraop Series selection")
    dataSectionFormLayout.addRow(self.step3frame)
    step3Layout = qt.QFormLayout(self.step3frame)

    # create ListView for intraop series selection
    self.seriesView = qt.QListView()
    self.seriesView.setObjectName('SeriesTable')
    self.seriesView.setSpacing(3)
    self.seriesModel = qt.QStandardItemModel()
    self.seriesModel.setHorizontalHeaderLabels(['Series ID'])
    self.seriesView.setModel(self.seriesModel)
    self.seriesView.setSelectionMode(qt.QAbstractItemView.ExtendedSelection)
    # self.seriesView.connect('clicked(QModelIndex)', self.seriesSelected)
    self.seriesView.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
    step3Layout.addWidget(self.seriesView)

    # Load Series into Slicer Button
    self.loadIntraopDataButton = qt.QPushButton("Load Series into Slicer")
    self.loadIntraopDataButton.toolTip = "Load Series into Slicer"
    self.loadIntraopDataButton.enabled = True
    dataSectionFormLayout.addWidget(self.loadIntraopDataButton)



    #
    # Step 2: Label Selection
    #


    labelSelectionCollapsibleButton = ctk.ctkCollapsibleButton()
    labelSelectionCollapsibleButton.text = "Step 2: Label Selection"
    self.layout.addWidget(labelSelectionCollapsibleButton)

    # Layout within the dummy collapsible button
    labelSelectionFormLayout = qt.QFormLayout(labelSelectionCollapsibleButton)

    #
    # preop label selector
    #

    self.preopLabelSelector = slicer.qMRMLNodeComboBox()
    self.preopLabelSelector.nodeTypes = ( ("vtkMRMLScalarVolumeNode"), "" )
    self.preopLabelSelector.addAttribute( "vtkMRMLScalarVolumeNode", "LabelMap", 0 )
    self.preopLabelSelector.selectNodeUponCreation = True
    self.preopLabelSelector.addEnabled = False
    self.preopLabelSelector.removeEnabled = False
    self.preopLabelSelector.noneEnabled = False
    self.preopLabelSelector.showHidden = False
    self.preopLabelSelector.showChildNodeTypes = False
    self.preopLabelSelector.setMRMLScene( slicer.mrmlScene )
    self.preopLabelSelector.setToolTip( "Pick the input to the algorithm." )
    labelSelectionFormLayout.addRow("Preop Image label: ", self.preopLabelSelector)

    #
    # intraop label selector
    #


    self.intraopLabelSelector = slicer.qMRMLNodeComboBox()
    self.intraopLabelSelector.nodeTypes = ( ("vtkMRMLScalarVolumeNode"), "" )
    self.intraopLabelSelector.addAttribute( "vtkMRMLScalarVolumeNode", "LabelMap", 0 )
    self.intraopLabelSelector.selectNodeUponCreation = True
    self.intraopLabelSelector.addEnabled = False
    self.intraopLabelSelector.removeEnabled = False
    self.intraopLabelSelector.noneEnabled = False
    self.intraopLabelSelector.showHidden = False
    self.intraopLabelSelector.showChildNodeTypes = False
    self.intraopLabelSelector.setMRMLScene( slicer.mrmlScene )
    self.intraopLabelSelector.setToolTip( "Pick the input to the algorithm." )
    labelSelectionFormLayout.addRow("Intraop Image label: ", self.intraopLabelSelector)

    #
    # reference volume selector
    #

    self.referenceVolumeSelector = slicer.qMRMLNodeComboBox()
    self.referenceVolumeSelector.nodeTypes = ( ("vtkMRMLScalarVolumeNode"), "" )
    self.referenceVolumeSelector.selectNodeUponCreation = True
    self.referenceVolumeSelector.addEnabled = False
    self.referenceVolumeSelector.removeEnabled = False
    self.referenceVolumeSelector.noneEnabled = False
    self.referenceVolumeSelector.showHidden = False
    self.referenceVolumeSelector.showChildNodeTypes = False
    self.referenceVolumeSelector.setMRMLScene( slicer.mrmlScene )
    self.referenceVolumeSelector.setToolTip( "Pick the input to the algorithm." )
    labelSelectionFormLayout.addRow("Reference Volume: ", self.referenceVolumeSelector)


    #
    # Quick Organ Segmentation Button
    #
    self.startSegmentationButton = qt.QPushButton("Start Prostate Segmentation")
    self.startSegmentationButton.enabled = True
    labelSelectionFormLayout.addRow(self.startSegmentationButton)

    #
    # Apply Segmentation
    #

    self.applySegmentationButton = qt.QPushButton("Apply Segmentation")
    self.applySegmentationButton.toolTip = "Run the algorithm."
    self.applySegmentationButton.enabled = True
    labelSelectionFormLayout.addRow(self.applySegmentationButton)

    # connections
    self.startSegmentationButton.connect('clicked(bool)', self.onStartSegmentationButton)
    self.applySegmentationButton.connect('clicked(bool)', self.onApplySegmentationButton)
    self.watchIntraopCheckbox.connect('clicked(bool)', self.initializeListener)
    # add condition: watchIntraopCheckbox needs to be clicked AND checked == True
    self.loadIntraopDataButton.connect('clicked(bool)',self.loadSeriesIntoSlicer)



    #
    # Step 3: Registration
    #



    registrationSectionCollapsibleButton = ctk.ctkCollapsibleButton()
    registrationSectionCollapsibleButton.text = "Step 3: Registration"
    self.layout.addWidget(registrationSectionCollapsibleButton)

    # Layout within the dummy collapsible button
    registrationSectionFormLayout = qt.QFormLayout(registrationSectionCollapsibleButton)

    #
    # preop volume selector
    #

    self.preopLabelSelector = slicer.qMRMLNodeComboBox()
    self.preopLabelSelector.nodeTypes = ( ("vtkMRMLScalarVolumeNode"), "" )
    self.preopLabelSelector.addAttribute( "vtkMRMLScalarVolumeNode", "LabelMap", 0 )
    self.preopLabelSelector.selectNodeUponCreation = True
    self.preopLabelSelector.addEnabled = False
    self.preopLabelSelector.removeEnabled = False
    self.preopLabelSelector.noneEnabled = False
    self.preopLabelSelector.showHidden = False
    self.preopLabelSelector.showChildNodeTypes = False
    self.preopLabelSelector.setMRMLScene( slicer.mrmlScene )
    self.preopLabelSelector.setToolTip( "Pick the input to the algorithm." )
    registrationSectionFormLayout.addRow("Preop Image Volume: ", self.preopLabelSelector)

    #
    # preop label selector
    #

    self.preopLabelSelector = slicer.qMRMLNodeComboBox()
    self.preopLabelSelector.nodeTypes = ( ("vtkMRMLScalarVolumeNode"), "" )
    self.preopLabelSelector.addAttribute( "vtkMRMLScalarVolumeNode", "LabelMap", 0 )
    self.preopLabelSelector.selectNodeUponCreation = True
    self.preopLabelSelector.addEnabled = False
    self.preopLabelSelector.removeEnabled = False
    self.preopLabelSelector.noneEnabled = False
    self.preopLabelSelector.showHidden = False
    self.preopLabelSelector.showChildNodeTypes = False
    self.preopLabelSelector.setMRMLScene( slicer.mrmlScene )
    self.preopLabelSelector.setToolTip( "Pick the input to the algorithm." )
    registrationSectionFormLayout.addRow("Preop Label Volume: ", self.preopLabelSelector)

    #
    # intraop volume selector
    #

    self.preopLabelSelector = slicer.qMRMLNodeComboBox()
    self.preopLabelSelector.nodeTypes = ( ("vtkMRMLScalarVolumeNode"), "" )
    self.preopLabelSelector.addAttribute( "vtkMRMLScalarVolumeNode", "LabelMap", 0 )
    self.preopLabelSelector.selectNodeUponCreation = True
    self.preopLabelSelector.addEnabled = False
    self.preopLabelSelector.removeEnabled = False
    self.preopLabelSelector.noneEnabled = False
    self.preopLabelSelector.showHidden = False
    self.preopLabelSelector.showChildNodeTypes = False
    self.preopLabelSelector.setMRMLScene( slicer.mrmlScene )
    self.preopLabelSelector.setToolTip( "Pick the input to the algorithm." )
    registrationSectionFormLayout.addRow("Intraop Image Volume: ", self.preopLabelSelector)

    #
    # intraop label selector
    #

    self.preopLabelSelector = slicer.qMRMLNodeComboBox()
    self.preopLabelSelector.nodeTypes = ( ("vtkMRMLScalarVolumeNode"), "" )
    self.preopLabelSelector.addAttribute( "vtkMRMLScalarVolumeNode", "LabelMap", 0 )
    self.preopLabelSelector.selectNodeUponCreation = True
    self.preopLabelSelector.addEnabled = False
    self.preopLabelSelector.removeEnabled = False
    self.preopLabelSelector.noneEnabled = False
    self.preopLabelSelector.showHidden = False
    self.preopLabelSelector.showChildNodeTypes = False
    self.preopLabelSelector.setMRMLScene( slicer.mrmlScene )
    self.preopLabelSelector.setToolTip( "Pick the input to the algorithm." )
    registrationSectionFormLayout.addRow("Intraop Label Volume: ", self.preopLabelSelector)


    #
    # Apply Segmentation
    #

    self.applyRegistrationButton = qt.QPushButton("Apply Registration")
    self.applyRegistrationButton.toolTip = "Run the algorithm."
    self.applyRegistrationButton.enabled = True
    registrationSectionFormLayout.addRow(self.applyRegistrationButton)



    #
    # Step 4: Registration Evaluation
    #
    evaluationSectionCollapsibleButton = ctk.ctkCollapsibleButton()
    evaluationSectionCollapsibleButton.text = "Step 4: Evaluation"
    self.layout.addWidget(evaluationSectionCollapsibleButton)

    # Layout within the dummy collapsible button
    evaluationSectionFormLayout = qt.QFormLayout(evaluationSectionCollapsibleButton)


  def loadSeriesIntoSlicer(self):

    # TODO: Load only sections into slicer that are checked in Series Selection
    # try to load directory from entries in dicom database
    dcmList = []
    for dcm in os.listdir(self.intraopDirButton.directory):
      if len(dcm)-dcm.rfind('.dcm') == 4:
        dcmList.append(self.intraopDirButton.directory+'/'+dcm)

    print dcmList

    scalarVolumePlugin = slicer.modules.dicomPlugins['DICOMScalarVolumePlugin']()

    loadables = scalarVolumePlugin.examine([dcmList])

    print loadables

    if len(loadables) == 0:
      print 'Could not parse the DICOM Study!'
      exit()

    inputVolume = scalarVolumePlugin.load(loadables[0])
    slicer.mrmlScene.AddNode(inputVolume)
    print('Input volume loaded!')



  def cleanup(self):
    pass

  def waitingForSeriesToBeCompleted(self):

    print ('waiting for Series to be completed')
    # wait 5 seconds for series to be completed

    qt.QTimer.singleShot(5000,self.importDICOMseries)

  def importDICOMseries(self):

    newFileList= []
    seriesList= []
    indexer = ctk.ctkDICOMIndexer()
    db=slicer.dicomDatabase

    # create a List NewFileList that contains only new files in the intraop directory
    for item in os.listdir(self.intraopDirButton.directory):
      if item not in self.currentFileList:
        newFileList.append(item)

    # import file in DICOM database
    for file in newFileList:
     indexer.addFile(db,str(self.intraopDirButton.directory+'/'+file),None)

     # add Series to seriesList
     if db.fileValue(str(self.intraopDirButton.directory+'/'+file),'0008,103E') not in seriesList:
       importfile=str(self.intraopDirButton.directory+'/'+file)
       seriesList.append(db.fileValue(importfile,'0008,103E'))

    # create Checkable Item in GUI
    for item in seriesList:
       self.currentSeries=item
       self.currentItem=qt.QStandardItem(item)
       self.seriesModel.appendRow(self.currentItem)
       self.currentItem.setCheckable(1)

    print('DICOM import finished')
    print('Those series are imported')
    print seriesList

    # notify the user
    self.notifyUser(self.currentSeries)

    return None

  def createCurrentFileList(self):

    self.currentFileList=[]
    for item in os.listdir(self.intraopDirButton.directory):
      self.currentFileList.append(item)

    print self.currentFileList

  def initializeListener(self):
    numberOfFiles = len([item for item in os.listdir(self.intraopDirButton.directory)])
    self.temp=numberOfFiles
    self.setlastNumberOfFiles(numberOfFiles)
    self.createCurrentFileList()
    self.startTimer()

  def startTimer(self):
    numberOfFiles = len([item for item in os.listdir(self.intraopDirButton.directory)])
    # print ('number of files : ',numberOfFiles)

    if self.getlastNumberOfFiles() < numberOfFiles:
     self.waitingForSeriesToBeCompleted()

     self.setlastNumberOfFiles(numberOfFiles)
     qt.QTimer.singleShot(5000,self.startTimer)

    else:
     self.setlastNumberOfFiles(numberOfFiles)
     qt.QTimer.singleShot(5000,self.startTimer)

  def setlastNumberOfFiles(self,number):
    self.temp = number

  def getlastNumberOfFiles(self):
    return self.temp

  def notifyUser(self,seriesName):
    # create Pop-Up Window
    self.notifyUserWindow = qt.QDialog(slicer.util.mainWindow())
    self.notifyUserWindow.setWindowTitle("New Series")
    self.notifyUserWindow.setLayout(qt.QVBoxLayout())

    # create Text Label
    self.textLabel = qt.QLabel()
    self.notifyUserWindow.layout().addWidget(self.textLabel)
    self.textLabel.setText("New Series are ready to be imported")

    # create Push Button
    self.pushButton = qt.QPushButton("Import new series"+"  "+seriesName)
    self.notifyUserWindow.layout().addWidget(self.pushButton)

    # create Push Button
    self.pushButton2 = qt.QPushButton("Not Now")
    self.notifyUserWindow.layout().addWidget(self.pushButton2)
    self.notifyUserWindow.show()

  def startTimer1(self):
    print ('Timer started')

  def onStartSegmentationButton(self):
    logic = RegistrationModuleLogic()

    print("Run the algorithm")

    logic.run()

  def onApplySegmentationButton(self):
    logic = RegistrationModuleLogic()
    print("onApplySegmentationButton")

    # initialize Label Map
    outputLabelMap=slicer.vtkMRMLScalarVolumeNode()
    outputLabelMap.SetLabelMap(1)
    slicer.mrmlScene.AddNode(outputLabelMap)

    # get clippingModel Node
    clipModelNode=slicer.mrmlScene.GetNodesByName('clipModelNode')
    clippingModel=clipModelNode.GetItemAsObject(0)

    # run CLI-Module
    logic.modelToLabelmap(self.referenceVolumeSelector.currentNode(),clippingModel,outputLabelMap)

    # set Label Outline
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeRed").SetUseLabelOutline(True)
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeYellow").SetUseLabelOutline(True)
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeGreen").SetUseLabelOutline(True)
#
# RegistrationModuleLogic
#

class RegistrationModuleLogic(ScriptedLoadableModuleLogic):
  """This class should implement all the actual
  computation done by your module.  The interface
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget.
  Uses ScriptedLoadableModuleLogic base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def hasImageData(self,volumeNode):
    """This is a dummy logic method that
    returns true if the passed in volume
    node has valid image data
    """
    if not volumeNode:
      print('no volume node')
      return False
    if volumeNode.GetImageData() == None:
      print('no image data')
      return False
    return True

  def takeScreenshot(self,name,description,type=-1):
    # show the message even if not taking a screen shot
    self.delayDisplay(description)

    if self.enableScreenshots == 0:
      return

    lm = slicer.app.layoutManager()
    # switch on the type to get the requested window
    widget = 0
    if type == slicer.qMRMLScreenShotDialog.FullLayout:
      # full layout
      widget = lm.viewport()
    elif type == slicer.qMRMLScreenShotDialog.ThreeD:
      # just the 3D window
      widget = lm.threeDWidget(0).threeDView()
    elif type == slicer.qMRMLScreenShotDialog.Red:
      # red slice window
      widget = lm.sliceWidget("Red")
    elif type == slicer.qMRMLScreenShotDialog.Yellow:
      # yellow slice window
      widget = lm.sliceWidget("Yellow")
    elif type == slicer.qMRMLScreenShotDialog.Green:
      # green slice window
      widget = lm.sliceWidget("Green")
    else:
      # default to using the full window
      widget = slicer.util.mainWindow()
      # reset the type so that the node is set correctly
      type = slicer.qMRMLScreenShotDialog.FullLayout

    # grab and convert to vtk image data
    qpixMap = qt.QPixmap().grabWidget(widget)
    qimage = qpixMap.toImage()
    imageData = vtk.vtkImageData()
    slicer.qMRMLUtils().qImageToVtkImageData(qimage,imageData)

    annotationLogic = slicer.modules.annotations.logic()
    annotationLogic.CreateSnapShot(name, description, type, self.screenshotScaleFactor, imageData)

  def run(self):
    """
    Run the actual algorithm
    """

    self.delayDisplay('Running the aglorithm')

    # set four up view, select persistent fiducial marker as crosshair
    self.setVolumeClipUserMode()

    # let user place Fiducials
    self.placeFiducials()

    return True



  def setVolumeClipUserMode(self):

    # set Four Up View
    lm=slicer.app.layoutManager()
    lm.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView)

    # set the mouse mode into Markups fiducial placement
    placeModePersistence = 1
    slicer.modules.markups.logic().StartPlaceMode(placeModePersistence)

    return True

  def updateModel(self,observer,caller):

    clipModelNode=slicer.mrmlScene.GetNodesByName('clipModelNode')
    clippingModel=clipModelNode.GetItemAsObject(0)

    inputMarkupNode=slicer.mrmlScene.GetNodesByName('inputMarkupNode')
    inputMarkup=inputMarkupNode.GetItemAsObject(0)

    import VolumeClipWithModel
    clipLogic=VolumeClipWithModel.VolumeClipWithModelLogic()
    clipLogic.updateModelFromMarkup(inputMarkup, clippingModel)

  def placeFiducials(self):

    # Create empty model node
    clippingModel = slicer.vtkMRMLModelNode()
    clippingModel.SetName('clipModelNode')
    slicer.mrmlScene.AddNode(clippingModel)

    # Create markup display fiducials - why do i need that?
    displayNode = slicer.vtkMRMLMarkupsDisplayNode()
    slicer.mrmlScene.AddNode(displayNode)

    # create markup fiducial node
    inputMarkup = slicer.vtkMRMLMarkupsFiducialNode()
    inputMarkup.SetName('inputMarkupNode')
    slicer.mrmlScene.AddNode(inputMarkup)
    inputMarkup.SetAndObserveDisplayNodeID(displayNode.GetID())

    # add Observer
    inputMarkup.AddObserver(vtk.vtkCommand.ModifiedEvent,self.updateModel)

    return True

  def modelToLabelmap(self,inputVolume,inputModel,outputLabelMap):

    """
    PARAMETER FOR MODELTOLABELMAP CLI MODULE:
    Parameter (0/0): sampleDistance
    Parameter (0/1): labelValue
    Parameter (1/0): InputVolume
    Parameter (1/1): surface
    Parameter (1/2): OutputVolume
    """

    # define params
    params = {'sampleDistance': 0.1, 'labelValue': 5, 'InputVolume' : inputVolume, 'surface' : inputModel, 'OutputVolume' : outputLabelMap}

    # run ModelToLabelMap-CLI Module
    slicer.cli.run(slicer.modules.modeltolabelmap, None, params)

    return True


class RegistrationModuleTest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  Uses ScriptedLoadableModuleTest base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setUp(self):
    """ Do whatever is needed to reset the state - typically a scene clear will be enough.
    """
    slicer.mrmlScene.Clear(0)

  def runTest(self):
    """Run as few or as many tests as needed here.
    """
    self.setUp()
    self.test_RegistrationModule1()

  def test_RegistrationModule1(self):
    """ Ideally you should have several levels of tests.  At the lowest level
    tests sould exercise the functionality of the logic with different inputs
    (both valid and invalid).  At higher levels your tests should emulate the
    way the user would interact with your code and confirm that it still works
    the way you intended.
    One of the most important features of the tests is that it should alert other
    developers when their changes will have an impact on the behavior of your
    module.  For example, if a developer removes a feature that you depend on,
    your test should break so they know that the feature is needed.
    """
    self.intraopDirButton.directory='/Users/peterbehringer/MyImageData/Test_PreopAnnotationDir/targets.fcsv'
