import os
import unittest
from __main__ import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from Editor import EditorWidget
from EditorLib import EditColor
import Editor
from EditorLib import EditUtil
from EditorLib import EditorLib


#
# RegistrationModule
#

class RegistrationModule(ScriptedLoadableModule):

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "RegistrationModule"
    self.parent.categories = ["Examples"]
    self.parent.dependencies = []
    self.parent.contributors = ["Peter Behringer (SPL), Andriy Fedorov (SPL)"]
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
    self.settings = qt.QSettings() #TODO: write path settings as in PCAMP Review
    self.temp = None

    # Create PushButtons for Workflow-Steps 1-4

    # Set Icon Size for the 4 Icon Items
    size=qt.QSize(120,120)

    # Create Data Selection Button
    pixmap=qt.QPixmap('/Users/peterbehringer/MyDevelopment/Icons/icon-dataselection1.png')
    icon=qt.QIcon(pixmap)
    dataButton=qt.QPushButton()
    dataButton.setIcon(icon)
    dataButton.setIconSize(size)
    dataButton.setFixedHeight(60)
    dataButton.setFixedWidth(140)
    dataButton.setStyleSheet("background-color: rgb(255,255,255)")


    # Create Label Selection Button
    pixmap=qt.QPixmap('/Users/peterbehringer/MyDevelopment/Icons/icon-dataselection2.png')
    icon=qt.QIcon(pixmap)
    labelButton=qt.QPushButton()
    labelButton.setIcon(icon)
    labelButton.setIconSize(size)
    labelButton.setFixedHeight(60)
    labelButton.setFixedWidth(140)
    labelButton.setStyleSheet("background-color: rgb(255,255,255)")

    # Create Registration Button
    pixmap=qt.QPixmap('/Users/peterbehringer/MyDevelopment/Icons/icon-dataselection3.png')
    icon=qt.QIcon(pixmap)
    regButton=qt.QPushButton()
    regButton.setIcon(icon)
    regButton.setIconSize(size)
    regButton.setFixedHeight(60)
    regButton.setFixedWidth(140)
    regButton.setStyleSheet("background-color: rgb(255,255,255)")


    # Create Data Selection Button
    pixmap=qt.QPixmap('/Users/peterbehringer/MyDevelopment/Icons/icon-dataselection4.png')
    icon=qt.QIcon(pixmap)
    evalButton=qt.QPushButton()
    evalButton.setIcon(icon)
    evalButton.setIconSize(size)
    evalButton.setFixedHeight(60)
    evalButton.setFixedWidth(140)
    evalButton.setStyleSheet("background-color: rgb(255,255,255)")

    # connections

    evalButton.connect('clicked(bool)',self.onStep4Evaluation)
    regButton.connect('clicked(bool)',self.onStep3Registration)
    labelButton.connect('clicked(bool)',self.onStep2LabelSelection)
    dataButton.connect('clicked(bool)',self.onStep1DataSelection)

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
    self.dataSectionCollapsibleButton = ctk.ctkCollapsibleButton()
    self.dataSectionCollapsibleButton.text = "Step 1: Data Selection"
    self.layout.addWidget(self.dataSectionCollapsibleButton)

    # Layout within the collapsible Button section
    dataSectionFormLayout = qt.QFormLayout(self.dataSectionCollapsibleButton)

    # Layout within a row of that section
    selectPatientRowLayout = qt.QHBoxLayout()

    # Create PatientSelector
    patientSelector=ctk.ctkComboBox()
    selectPatientRowLayout.addWidget(patientSelector)
    dataSectionFormLayout.addRow("Select Patient: ", selectPatientRowLayout)

    # TODO: Update Section if database changed

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
    self.layout.addStretch(1)

    # set Directory to my Test folder
    self.intraopDirButton.directory='/Applications/A_INTRAOP_DIR'
    self.preopDirButton.directory='/Applications/A_PREOP_DIR'

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

    """
    # TEST BUTTON
    self.testButton = qt.QPushButton("Test Button")
    self.testButton.toolTip = "Test Button"
    self.testButton.enabled = True
    dataSectionFormLayout.addWidget(self.testButton)

    # TEST BUTTON II
    self.testButton2 = qt.QPushButton("Show selected")
    self.testButton2.toolTip = "Test Button"
    self.testButton2.enabled = True
    dataSectionFormLayout.addWidget(self.testButton2)
    """



    #
    # Step 2: Label Selection
    #


    self.labelSelectionCollapsibleButton = ctk.ctkCollapsibleButton()
    self.labelSelectionCollapsibleButton.text = "Step 2: Label Selection"
    self.labelSelectionCollapsibleButton.collapsed=0
    self.labelSelectionCollapsibleButton.hide()
    self.layout.addWidget(self.labelSelectionCollapsibleButton)

    # Layout within the collapsible button
    labelSelectionFormLayout = qt.QFormLayout(self.labelSelectionCollapsibleButton)

    #labelSelectionFormLayout.setFormAlignment(0x0020)
    #
    # preop label selector
    #

    self.preopLabelSelector = slicer.qMRMLNodeComboBox()
    self.preopLabelSelector.nodeTypes = ( ("vtkMRMLScalarVolumeNode"), "" )
    self.preopLabelSelector.addAttribute( "vtkMRMLScalarVolumeNode", "LabelMap", 1 )
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
    self.intraopLabelSelector.addAttribute( "vtkMRMLScalarVolumeNode", "LabelMap", 1 )
    self.intraopLabelSelector.selectNodeUponCreation = True
    self.intraopLabelSelector.addEnabled = False
    self.intraopLabelSelector.removeEnabled = False
    self.intraopLabelSelector.noneEnabled = True
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
    self.referenceVolumeSelector.addAttribute( "vtkMRMLScalarVolumeNode", "LabelMap", 0 )
    self.referenceVolumeSelector.selectNodeUponCreation = True
    self.referenceVolumeSelector.addEnabled = False
    self.referenceVolumeSelector.removeEnabled = False
    self.referenceVolumeSelector.noneEnabled = True
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
    labelSelectionFormLayout.addWidget(self.applySegmentationButton)

    #
    # Editor Widget
    #


    self.editUtil = EditorLib.EditUtil.EditUtil()
    editorWidgetParent = slicer.qMRMLWidget()
    editorWidgetParent.setLayout(qt.QVBoxLayout())
    editorWidgetParent.setMRMLScene(slicer.mrmlScene)
    self.editorWidget = EditorWidget(parent=editorWidgetParent,showVolumesFrame=False)
    self.editorWidget.setup()
    self.editorParameterNode = self.editUtil.getParameterNode()
    labelSelectionFormLayout.addRow(editorWidgetParent)



    # connections
    self.startSegmentationButton.connect('clicked(bool)', self.onStartSegmentationButton)
    self.applySegmentationButton.connect('clicked(bool)', self.onApplySegmentationButton)
    self.watchIntraopCheckbox.connect('clicked(bool)', self.initializeListener)
    # TODO add condition: watchIntraopCheckbox needs to be clicked AND checked == True
    self.loadIntraopDataButton.connect('clicked(bool)',self.loadSeriesIntoSlicer)
    self.loadPreopDataButton.connect('clicked(bool)',self.loadPreopData)
    #self.testButton.connect('clicked(bool)',self.testFunction)
    #self.testButton2.connect('clicked(bool)',self.testFunction2)





    #
    # Step 3: Registration
    #


    self.registrationSectionCollapsibleButton = ctk.ctkCollapsibleButton()
    self.registrationSectionCollapsibleButton.text = "Step 3: Registration"
    self.layout.addWidget(self.registrationSectionCollapsibleButton)
    self.registrationSectionCollapsibleButton.collapsed=0
    self.registrationSectionCollapsibleButton.hide()

    # Layout within the dummy collapsible button
    registrationSectionFormLayout = qt.QFormLayout(self.registrationSectionCollapsibleButton)



    #
    # preop volume selector
    #

    self.preopVolumeSelector = slicer.qMRMLNodeComboBox()
    self.preopVolumeSelector.nodeTypes = ( ("vtkMRMLScalarVolumeNode"), "" )
    self.preopVolumeSelector.addAttribute( "vtkMRMLScalarVolumeNode", "LabelMap", 0 )
    self.preopVolumeSelector.selectNodeUponCreation = True
    self.preopVolumeSelector.addEnabled = False
    self.preopVolumeSelector.removeEnabled = False
    self.preopVolumeSelector.noneEnabled = False
    self.preopVolumeSelector.showHidden = False
    self.preopVolumeSelector.showChildNodeTypes = False
    self.preopVolumeSelector.setMRMLScene( slicer.mrmlScene )
    self.preopVolumeSelector.setToolTip( "Pick the input to the algorithm." )
    registrationSectionFormLayout.addRow("Preop Image Volume: ", self.preopVolumeSelector)

    #
    # preop label selector
    #

    self.preopLabelSelector = slicer.qMRMLNodeComboBox()
    self.preopLabelSelector.nodeTypes = ( ("vtkMRMLScalarVolumeNode"), "" )
    self.preopLabelSelector.addAttribute( "vtkMRMLScalarVolumeNode", "LabelMap", 1 )
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

    self.intraopVolumeSelector = slicer.qMRMLNodeComboBox()
    self.intraopVolumeSelector.nodeTypes = ( ("vtkMRMLScalarVolumeNode"), "" )
    self.intraopVolumeSelector.addAttribute( "vtkMRMLScalarVolumeNode", "LabelMap", 0 )
    self.intraopVolumeSelector.selectNodeUponCreation = True
    self.intraopVolumeSelector.addEnabled = False
    self.intraopVolumeSelector.removeEnabled = False
    self.intraopVolumeSelector.noneEnabled = True
    self.intraopVolumeSelector.showHidden = False
    self.intraopVolumeSelector.showChildNodeTypes = False
    self.intraopVolumeSelector.setMRMLScene( slicer.mrmlScene )
    self.intraopVolumeSelector.setToolTip( "Pick the input to the algorithm." )
    registrationSectionFormLayout.addRow("Intraop Image Volume: ", self.intraopVolumeSelector)

    #
    # intraop label selector
    #

    self.intraopLabelSelector = slicer.qMRMLNodeComboBox()
    self.intraopLabelSelector.nodeTypes = ( ("vtkMRMLScalarVolumeNode"), "" )
    self.intraopLabelSelector.addAttribute( "vtkMRMLScalarVolumeNode", "LabelMap", 0 )
    self.intraopLabelSelector.selectNodeUponCreation = True
    self.intraopLabelSelector.addEnabled = False
    self.intraopLabelSelector.removeEnabled = False
    self.intraopLabelSelector.noneEnabled = True
    self.intraopLabelSelector.showHidden = False
    self.intraopLabelSelector.showChildNodeTypes = False
    self.intraopLabelSelector.setMRMLScene( slicer.mrmlScene )
    self.intraopLabelSelector.setToolTip( "Pick the input to the algorithm." )
    registrationSectionFormLayout.addRow("Intraop Label Volume: ", self.intraopLabelSelector)


    #
    # Apply Registration
    #

    self.applyRegistrationButton = qt.QPushButton("Apply Registration")
    self.applyRegistrationButton.toolTip = "Run the algorithm."
    self.applyRegistrationButton.enabled = True
    registrationSectionFormLayout.addRow(self.applyRegistrationButton)
    self.applyRegistrationButton.connect('clicked(bool)',RegistrationModuleLogic().applyRegistration)


    #
    # Step 4: Registration Evaluation
    #
    self.evaluationSectionCollapsibleButton = ctk.ctkCollapsibleButton()
    self.evaluationSectionCollapsibleButton.text = "Step 4: Evaluation"

    self.layout.addWidget(self.evaluationSectionCollapsibleButton)
    self.evaluationSectionCollapsibleButton.collapsed=0
    self.evaluationSectionCollapsibleButton.hide()

    # Layout within the dummy collapsible button
    evaluationSectionFormLayout = qt.QFormLayout(self.evaluationSectionCollapsibleButton)
    tryLayout = qt.QHBoxLayout()
    evaluationSectionFormLayout.addRow("Select Patient: ", tryLayout)


  def onStep1DataSelection(self):

    self.dataSectionCollapsibleButton.show()
    self.labelSelectionCollapsibleButton.show()
    self.registrationSectionCollapsibleButton.show()
    self.evaluationSectionCollapsibleButton.show()

  def onStep2LabelSelection(self):
    self.dataSectionCollapsibleButton.hide()
    self.labelSelectionCollapsibleButton.show()
    self.registrationSectionCollapsibleButton.hide()
    self.evaluationSectionCollapsibleButton.hide()

  def onStep3Registration(self):
    self.dataSectionCollapsibleButton.hide()
    self.labelSelectionCollapsibleButton.hide()
    self.registrationSectionCollapsibleButton.show()
    self.evaluationSectionCollapsibleButton.hide()

  def onStep4Evaluation(self):
    self.dataSectionCollapsibleButton.hide()
    self.labelSelectionCollapsibleButton.hide()
    self.registrationSectionCollapsibleButton.hide()
    self.evaluationSectionCollapsibleButton.show()


  def loadPreopData(self):

    # this function finds all volumes and fiducials in a directory and loads them into slicer

    fidList=[]
    volumeList=[]
    labelList=[]

    for nrrd in os.listdir(self.preopDirButton.directory):
      if len(nrrd)-nrrd.rfind('.nrrd') == 5:
        volumeList.append(self.preopDirButton.directory+'/'+nrrd)

    print ('volumes found :')
    print volumeList

    for fcsv in os.listdir(self.preopDirButton.directory):
      if len(fcsv)-fcsv.rfind('.fcsv') == 5:
        fidList.append(self.preopDirButton.directory+'/'+fcsv)

    print ('fiducials found :')
    print fidList

    # TODO: distinguish between image data volumes and labelmaps

    # load testdata and create Nodes
    preoplabelVolume=slicer.util.loadLabelVolume('/Applications/A_PREOP_DIR/Case1-t2ax-TG-rater1.nrrd')
    preoplabelVolumeNode=slicer.mrmlScene.GetNodesByName('Case1-t2ax-TG-rater1').GetItemAsObject(0)

    preopImageVolume=slicer.util.loadVolume('/Applications/A_PREOP_DIR/Case1-t2ax-N4.nrrd')
    preopImageVolumeNode=slicer.mrmlScene.GetNodesByName('Case1-t2ax-N4').GetItemAsObject(0)

    preopTargets=slicer.util.loadMarkupsFiducialList('/Applications/A_PREOP_DIR/Case1-landmarks.fcsv')
    preopTargetsNode=slicer.mrmlScene.GetNodesByName('case1-landmarks').GetItemAsObject(0)

    # use label contours
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeRed").SetUseLabelOutline(True)
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeYellow").SetUseLabelOutline(True)
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeGreen").SetUseLabelOutline(True)

    # rotate volume to plane
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeRed").RotateToVolumePlane(preopImageVolumeNode)
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeYellow").RotateToVolumePlane(preopImageVolumeNode)
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeGreen").RotateToVolumePlane(preopImageVolumeNode)

    # set Layout to redSliceViewOnly
    lm=slicer.app.layoutManager()
    lm.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)

    # fit Slice View to FOV
    red=lm.sliceWidget('Red')
    redLogic=red.sliceLogic()
    redLogic.FitSliceToAll()

    # set markups visible
    markupsLogic=slicer.modules.markups.logic()
    markupsLogic.SetAllMarkupsVisibility(preopTargetsNode,1)

    # jump to markup slice
    # slicer.modules.markups.logic().JumpSlicesToNthPointInMarkup(preopTargetsNode, index, 1)



  def testFunction(self):

    print ('Hello')

    seriesList=[]
    series1='3 plane loc'
    series2='AX FSPGR FS T1 PRE'
    seriesList.append(series1)
    seriesList.append(series2)

    self.seriesModel.clear()
    self.seriesItems = []
    print seriesList

    for s in range(len(seriesList)):
      seriesText = seriesList[s]
      sItem = qt.QStandardItem(seriesText)
      self.seriesItems.append(sItem)
      self.seriesModel.appendRow(sItem)
      sItem.setCheckable(1)

   # self.createLoadableFileListFromSelection()

  def testFunction2(self):

   return None

  def getSelectedSeriesFromSelector(self):

    # this function returns a List of names of the series
    # that are selected in Intraop Series Selector

    checkedItems = [x for x in self.seriesItems if x.checkState()]
    self.selectedSeries=[]

    for x in checkedItems:
      self.selectedSeries.append(x.text())

    return self.selectedSeries

  def createLoadableFileListFromSelection(self):

    # create dcmFileList that lists all .dcm files in directory
    dcmFileList = []
    self.selectedFileList=[]
    db=slicer.dicomDatabase

    for dcm in os.listdir(self.intraopDirButton.directory):
      if len(dcm)-dcm.rfind('.dcm') == 4:
        dcmFileList.append(self.intraopDirButton.directory+'/'+dcm)

    # get the selected Series List
    selectedSeriesList=self.getSelectedSeriesFromSelector()

    # write all selected files in selectedFileList
    for file in dcmFileList:
     if db.fileValue(file,'0008,103E') in selectedSeriesList:
       self.selectedFileList.append(file)

  def loadSeriesIntoSlicer(self):

    self.createLoadableFileListFromSelection()

    # create DICOMScalarVolumePlugin and load selectedSeries data from files into slicer
    scalarVolumePlugin = slicer.modules.dicomPlugins['DICOMScalarVolumePlugin']()

    try:
      loadables = scalarVolumePlugin.examine([self.selectedFileList])
    except:
      print ('There is nothing to load. You have to select series')


    for s in range(len(self.selectedSeries)):
     inputVolume = scalarVolumePlugin.load(loadables[s])
     # inputVolume.setName(selectedSeries[s])

     # TODO: change name of imported series; right now its still very strange
     slicer.mrmlScene.AddNode(inputVolume)
     print('Input volume '+str(s)+' : '+self.selectedSeries[s]+' loaded!')

     # added: print name
     print('name is ')
     print(str(inputVolume))

    # TODO:
    # set inputVolume Node as Reference Volume in Label Selection
    # set inputVolume Node as Intraop Image Volume in Registration




  def cleanup(self):
    pass

  def waitingForSeriesToBeCompleted(self):

    print ('***** New Data in intraop directory detected ***** ')
    print ('waiting 5 more seconds for Series to be completed')

    qt.QTimer.singleShot(5000,self.importDICOMseries)

  def importDICOMseries(self):

    newFileList= []
    self.seriesList= []
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
     if db.fileValue(str(self.intraopDirButton.directory+'/'+file),'0008,103E') not in self.seriesList:
       importfile=str(self.intraopDirButton.directory+'/'+file)
       self.seriesList.append(db.fileValue(importfile,'0008,103E'))

    # create Checkable Item in GUI

    self.seriesModel.clear()
    self.seriesItems = []

    for s in range(len(self.seriesList)):
      seriesText = self.seriesList[s]
      self.currentSeries=seriesText
      sItem = qt.QStandardItem(seriesText)
      self.seriesItems.append(sItem)
      self.seriesModel.appendRow(sItem)
      sItem.setCheckable(1)

    print('DICOM import finished')
    print('Those series are imported')
    print self.seriesList

    # notify the user

    # self.notifyUser(self.currentSeries)

  def createCurrentFileList(self):

    self.currentFileList=[]
    for item in os.listdir(self.intraopDirButton.directory):
      self.currentFileList.append(item)

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
    self.pushButton.connect('clicked(bool)',self.loadSeriesIntoSlicer)


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
    outputLabelMap.SetName('Intraop Label Map')
    slicer.mrmlScene.AddNode(outputLabelMap)

    # get clippingModel Node
    clipModelNode=slicer.mrmlScene.GetNodesByName('clipModelNode')
    clippingModel=clipModelNode.GetItemAsObject(0)

    # run CLI-Module
    logic.modelToLabelmap(self.referenceVolumeSelector.currentNode(),clippingModel,outputLabelMap)
    """
    clipModelNode=slicer.mrmlScene.GetNodesByName('clipModelNode')
    clippingModel=clipModelNode.GetItemAsObject(0)
    slicer.mrmlScene.RemoveNode(clippingModel)
    """



    # use label contours
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeRed").SetUseLabelOutline(True)
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeYellow").SetUseLabelOutline(True)
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeGreen").SetUseLabelOutline(True)
    """
    # rotate volume to plane
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeRed").RotateToVolumePlane(outputLabelMap)
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeYellow").RotateToVolumePlane(outputLabelMap)
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeGreen").RotateToVolumePlane(outputLabelMap)
    """
    # set Layout to redSliceViewOnly
    lm=slicer.app.layoutManager()
    lm.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)

    # fit Slice View to FOV
    red=lm.sliceWidget('Red')
    redLogic=red.sliceLogic()
    redLogic.FitSliceToAll()






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

    # set Layout to redSliceViewOnly
    lm=slicer.app.layoutManager()
    lm.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)

    # fit Slice View to FOV
    red=lm.sliceWidget('Red')
    redLogic=red.sliceLogic()
    redLogic.FitSliceToAll()

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
    params = {'sampleDistance': 0.1, 'labelValue': 1, 'InputVolume' : inputVolume, 'surface' : inputModel, 'OutputVolume' : outputLabelMap}

    # run ModelToLabelMap-CLI Module
    slicer.cli.run(slicer.modules.modeltolabelmap, None, params)

    return True


  def runBRAINSFit(self,movingImage,fixedImage,movingImageLabel,fixedImageLabel):

    # rigidly register followup to baseline
    # TODO: do this in a separate step and allow manual adjustment?
    # TODO: add progress reporting (BRAINSfit does not report progress though)
    pNode = self.parameterNode()
    baselineVolumeID = pNode.GetParameter('baselineVolumeID')
    followupVolumeID = pNode.GetParameter('followupVolumeID')
    self.__followupTransform = slicer.vtkMRMLLinearTransformNode()
    slicer.mrmlScene.AddNode(self.__followupTransform)

    parameters = {}
    parameters["fixedVolume"] = baselineVolumeID
    parameters["movingVolume"] = followupVolumeID
    parameters["initializeTransformMode"] = "useMomentsAlign"
    parameters["useRigid"] = True
    parameters["useScaleVersor3D"] = True
    parameters["useScaleSkewVersor3D"] = True
    parameters["useAffine"] = True
    parameters["linearTransform"] = self.__followupTransform.GetID()

    self.__cliNode = None
    self.__cliNode = slicer.cli.run(slicer.modules.brainsfit, self.__cliNode, parameters)

    self.__cliObserverTag = self.__cliNode.AddObserver('ModifiedEvent', self.processRegistrationCompletion)
    self.__registrationStatus.setText('Wait ...')
    self.__registrationButton.setEnabled(0)

    """def processRegistrationCompletion(self, node, event):
    status = node.GetStatusString()
    self.__registrationStatus.setText('Registration '+status)
    if status == 'Completed':
      self.__registrationButton.setEnabled(1)

      pNode = self.parameterNode()
      followupNode = slicer.mrmlScene.GetNodeByID(pNode.GetParameter('followupVolumeID'))
      followupNode.SetAndObserveTransformNodeID(self.__followupTransform.GetID())

      Helper.SetBgFgVolumes(pNode.GetParameter('baselineVolumeID'),pNode.GetParameter('followupVolumeID'))

      pNode.SetParameter('followupTransformID', self.__followupTransform.GetID())"""

  def applyRegistration(self):

    cliModule = slicer.modules.brainsfit
    n=cliModule.cliModuleLogic().CreateNode()
    for groupIndex in xrange(0,n.GetNumberOfParameterGroups()):
      for parameterIndex in xrange(0,n.GetNumberOfParametersInGroup(groupIndex)):
        print '  Parameter ({0}/{1}): {2}'.format(groupIndex, parameterIndex, n.GetParameterName(groupIndex, parameterIndex))
    """
  Parameter (0/0): fixedVolume
  Parameter (0/1): movingVolume
  Parameter (0/2): samplingPercentage
  Parameter (0/3): splineGridSize
  Parameter (1/0): linearTransform
  Parameter (1/1): bsplineTransform
  Parameter (1/2): outputVolume
  Parameter (2/0): initialTransform
  Parameter (2/1): initializeTransformMode
  Parameter (3/0): useRigid
  Parameter (3/1): useScaleVersor3D
  Parameter (3/2): useScaleSkewVersor3D
  Parameter (3/3): useAffine
  Parameter (3/4): useBSpline
  Parameter (3/5): useSyN
  Parameter (3/6): useComposite
  Parameter (4/0): maskProcessingMode
  Parameter (4/1): fixedBinaryVolume
  Parameter (4/2): movingBinaryVolume
  Parameter (4/3): outputFixedVolumeROI
  Parameter (4/4): outputMovingVolumeROI
  Parameter (4/5): useROIBSpline
  Parameter (4/6): histogramMatch
  Parameter (4/7): medianFilterSize
  Parameter (4/8): removeIntensityOutliers
  Parameter (5/0): fixedVolume2
  Parameter (5/1): movingVolume2
  Parameter (5/2): outputVolumePixelType
  Parameter (5/3): backgroundFillValue
  Parameter (5/4): scaleOutputValues
  Parameter (5/5): interpolationMode
  Parameter (6/0): numberOfIterations
  Parameter (6/1): maximumStepLength
  Parameter (6/2): minimumStepLength
  Parameter (6/3): relaxationFactor
  Parameter (6/4): translationScale
  Parameter (6/5): reproportionScale
  Parameter (6/6): skewScale
  Parameter (6/7): maxBSplineDisplacement
  Parameter (7/0): fixedVolumeTimeIndex
  Parameter (7/1): movingVolumeTimeIndex
  Parameter (7/2): numberOfHistogramBins
  Parameter (7/3): numberOfMatchPoints
  Parameter (7/4): costMetric
  Parameter (7/5): maskInferiorCutOffFromCenter
  Parameter (7/6): ROIAutoDilateSize
  Parameter (7/7): ROIAutoClosingSize
  Parameter (7/8): numberOfSamples
  Parameter (7/9): strippedOutputTransform
  Parameter (7/10): transformType
  Parameter (7/11): outputTransform
  Parameter (7/12): initializeRegistrationByCurrentGenericTransform
  Parameter (8/0): failureExitCode
  Parameter (8/1): writeTransformOnFailure
  Parameter (8/2): numberOfThreads
  Parameter (8/3): debugLevel
  Parameter (8/4): costFunctionConvergenceFactor
  Parameter (8/5): projectedGradientTolerance
  Parameter (8/6): maximumNumberOfEvaluations
  Parameter (8/7): maximumNumberOfCorrections
  Parameter (8/8): UseDebugImageViewer
  Parameter (8/9): PromptAfterImageSend
  Parameter (8/10): metricSamplingStrategy
  Parameter (8/11): logFileReport
  """

    """
    PARAMETER FOR MODELTOLABELMAP CLI MODULE:
    Parameter (0/0): sampleDistance
    Parameter (0/1): labelValue
    Parameter (1/0): InputVolume
    Parameter (1/1): surface
    Parameter (1/2): OutputVolume
    """

    # define params
    params = {'sampleDistance': 0.1, 'labelValue': 1, 'InputVolume' : inputVolume, 'surface' : inputModel, 'OutputVolume' : outputLabelMap}

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
