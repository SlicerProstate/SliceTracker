import os
from __main__ import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from Editor import EditorWidget
import EditorLib
import logging


class RegistrationModule(ScriptedLoadableModule):

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "RegistrationModule"
    self.parent.categories = ["Registration"]
    self.parent.dependencies = ["VolumeClipWithModel"]
    self.parent.contributors = ["Peter Behringer (SPL), Andriy Fedorov (SPL)"]
    self.parent.helpText = """ Module for easy registration. """
    self.parent.acknowledgementText = """SPL, Brigham & Womens""" # replace with organization, grant and thanks.


class RegistrationModuleWidget(ScriptedLoadableModuleWidget):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  PATIENT_NAME          = '0010,0010'
  PATIENT_ID            = '0010,0020'
  PATIENT_BIRTH_DATE    = '0010,0030'
  SERIES_DESCRIPTION    = '0008,103E'
  ACQUISITION_TIME      = '0008,0032'
  
  STYLE_GRAY_BACKGROUND_WHITE_FONT  = 'background-color: rgb(130,130,130); ' \
                                      'color: rgb(255,255,255)'
  STYLE_WHITE_BACKGROUND            = 'background-color: rgb(255,255,255)'
  STYLE_LIGHT_GRAY_BACKGROUND       = 'background-color: rgb(230,230,230)'
  STYLE_ORANGE_BACKGROUND           = 'background-color: rgb(255,102,0)'

  def __init__(self, parent = None):
    ScriptedLoadableModuleWidget.__init__(self, parent)
    self.dicomDatabase = slicer.dicomDatabase

  def createPatientWatchBox(self):
    self.patientViewBox = qt.QGroupBox()
    self.patientViewBox.setStyleSheet(self.STYLE_LIGHT_GRAY_BACKGROUND)
    self.patientViewBox.setFixedHeight(80)
    self.patientViewBoxLayout = qt.QGridLayout()
    self.patientViewBox.setLayout(self.patientViewBoxLayout)
    self.patientViewBoxLayout.setColumnMinimumWidth(1, 50)
    self.patientViewBoxLayout.setColumnMinimumWidth(2, 50)
    self.patientViewBoxLayout.setHorizontalSpacing(0)
    self.layout.addWidget(self.patientViewBox)
    # create patient attributes
    self.categoryPatientID = qt.QLabel('Patient ID: ')
    self.patientViewBoxLayout.addWidget(self.categoryPatientID, 1, 1)
    self.categoryPatientName = qt.QLabel('Patient Name: ')
    self.patientViewBoxLayout.addWidget(self.categoryPatientName, 2, 1)
    self.categoryPatientBirthDate = qt.QLabel('Date of Birth: ')
    self.patientViewBoxLayout.addWidget(self.categoryPatientBirthDate, 3, 1)
    self.categoryStudyDate = qt.QLabel('Date of Study:')
    self.patientViewBoxLayout.addWidget(self.categoryStudyDate, 4, 1)
    self.patientID = qt.QLabel('None')
    self.patientViewBoxLayout.addWidget(self.patientID, 1, 2)
    self.patientName = qt.QLabel('None')
    self.patientViewBoxLayout.addWidget(self.patientName, 2, 2)
    self.patientBirthDate = qt.QLabel('None')
    self.patientViewBoxLayout.addWidget(self.patientBirthDate, 3, 2)
    self.studyDate = qt.QLabel('None')
    self.patientViewBoxLayout.addWidget(self.studyDate, 4, 2)

  def createTabWidget(self):
    # create TabWidget
    self.tabWidget = qt.QTabWidget()
    self.layout.addWidget(self.tabWidget)
    # get the TabBar
    self.tabBar = self.tabWidget.childAt(1, 1)
    # create Widgets inside each tab
    self.dataSelectionGroupBox = qt.QGroupBox()
    self.labelSelectionGroupBox = qt.QGroupBox()
    self.registrationGroupBox = qt.QGroupBox()
    self.evaluationGroupBox = qt.QGroupBox()
    # set up PixMaps
    self.dataSelectionIconPixmap = qt.QPixmap(self.modulePath + 'Resources/Icons/icon-dataselection_fit.png')
    self.labelSelectionIconPixmap = qt.QPixmap(self.modulePath + 'Resources/Icons/icon-labelselection_fit.png')
    self.registrationSectionPixmap = qt.QPixmap(self.modulePath + 'Resources/Icons/icon-registration_fit.png')
    self.evaluationSectionPixmap = qt.QPixmap(self.modulePath + 'Resources/Icons/icon-evaluation_fit.png')
    self.newImageDataPixmap = qt.QPixmap(self.modulePath + 'Resources/Icons/icon-newImageData.png')
    # set up Icons
    self.dataSelectionIcon = qt.QIcon(self.dataSelectionIconPixmap)
    self.labelSelectionIcon = qt.QIcon(self.labelSelectionIconPixmap)
    self.registrationSectionIcon = qt.QIcon(self.registrationSectionPixmap)
    self.evaluationSectionIcon = qt.QIcon(self.evaluationSectionPixmap)
    self.newImageDataIcon = qt.QIcon(self.newImageDataPixmap)
    self.tabWidget.setIconSize(qt.QSize(110, 50))
    # create Layout for each groupBox
    self.dataSelectionGroupBoxLayout = qt.QFormLayout()
    self.labelSelectionGroupBoxLayout = qt.QFormLayout()
    self.registrationGroupBoxLayout = qt.QFormLayout()
    self.evaluationGroupBoxLayout = qt.QFormLayout()
    # set Layout
    self.dataSelectionGroupBox.setLayout(self.dataSelectionGroupBoxLayout)
    self.labelSelectionGroupBox.setLayout(self.labelSelectionGroupBoxLayout)
    self.registrationGroupBox.setLayout(self.registrationGroupBoxLayout)
    self.evaluationGroupBox.setLayout(self.evaluationGroupBoxLayout)
    # add Tabs
    self.tabWidget.addTab(self.dataSelectionGroupBox, self.dataSelectionIcon, '')
    self.tabWidget.addTab(self.labelSelectionGroupBox, self.labelSelectionIcon, '')
    self.tabWidget.addTab(self.registrationGroupBox, self.registrationSectionIcon, '')
    self.tabWidget.addTab(self.evaluationGroupBox, self.evaluationSectionIcon, '')

  def createIncomeSimulationButtons(self):
    # Simulate DICOM Income 2
    self.simulateDataIncomeButton2 = qt.QPushButton("Simulate AMIGO Data Income 1")
    self.simulateDataIncomeButton2.toolTip = "Simulate Data Income 1: Localizer, COVER TEMPLATE, NEEDLE GUIDANCE 3"
    self.simulateDataIncomeButton2.enabled = True
    self.simulateDataIncomeButton2.setStyleSheet(self.STYLE_ORANGE_BACKGROUND)
    self.dataSelectionGroupBoxLayout.addWidget(self.simulateDataIncomeButton2)
    # Simulate DICOM Income 3
    self.simulateDataIncomeButton3 = qt.QPushButton("Simulate AMIGO Data Income 2")
    self.simulateDataIncomeButton3.toolTip = "Simulate Data Income 2"
    self.simulateDataIncomeButton3.enabled = True
    self.simulateDataIncomeButton3.setStyleSheet(self.STYLE_ORANGE_BACKGROUND)
    self.dataSelectionGroupBoxLayout.addWidget(self.simulateDataIncomeButton3)
    # Simulate DICOM Income 4
    self.simulateDataIncomeButton4 = qt.QPushButton("Simulate AMIGO Data Income 3")
    self.simulateDataIncomeButton4.toolTip = "Simulate Data Income 3"
    self.simulateDataIncomeButton4.enabled = True
    self.simulateDataIncomeButton4.setStyleSheet(self.STYLE_ORANGE_BACKGROUND)
    self.dataSelectionGroupBoxLayout.addWidget(self.simulateDataIncomeButton4)
    # HIDE ***
    self.simulateDataIncomeButton2.hide()
    self.simulateDataIncomeButton3.hide()
    self.simulateDataIncomeButton4.hide()

    self.simulateDataIncomeButton2.connect('clicked(bool)',self.onsimulateDataIncomeButton2)
    self.simulateDataIncomeButton3.connect('clicked(bool)',self.onsimulateDataIncomeButton3)
    self.simulateDataIncomeButton4.connect('clicked(bool)',self.onsimulateDataIncomeButton4)

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    # Parameters
    self.settings = qt.QSettings()
    self.modulePath = slicer.modules.registrationmodule.path.replace("RegistrationModule.py","")
    self.registrationResults = []
    self.intraopDataDir = ""
    self.preopDataDir = ""
    self.currentIntraopVolume = None
    self.currentIntraopLabel = None
    self.preopVolume = None
    self.preopLabel = None
    self.temp = None
    self.updatePatientSelectorFlag = True
    self.warningFlag = False
    self.patientNames = []
    self.patientIDs = []
    self.addedPatients = []
    self.selectablePatientItems=[]
    self.selectableRegistrationResults=[]
    self.seriesItems = []
    self.selectedSeries=[]
    self.rockCount = 0
    self.rocking = False
    self.rockTimer = None
    self.flickerTimer = None
    self.revealCursor = None
    self.deletedMarkups = slicer.vtkMRMLMarkupsFiducialNode()
    self.deletedMarkups.SetName('deletedMarkups')
    self.quickSegmentationFlag = 0
    self.labelSegmentationFlag = 0
    self.markupsLogic=slicer.modules.markups.logic()
    self.logic=RegistrationModuleLogic()
    self.comingFromPreopTag = False

    # set global slice widgets
    self.layoutManager=slicer.app.layoutManager()
    self.redWidget = self.layoutManager.sliceWidget('Red')
    self.yellowWidget = self.layoutManager.sliceWidget('Yellow')
    self.compositeNodeRed = self.redWidget.mrmlSliceCompositeNode()
    self.compositNodeYellow = self.yellowWidget.mrmlSliceCompositeNode()
    self.redSliceView=self.redWidget.sliceView()
    self.yellowSliceView=self.yellowWidget.sliceView()
    self.redSliceLogic=self.redWidget.sliceLogic()
    self.yellowSliceLogic=self.yellowWidget.sliceLogic()
    self.redSliceNode=self.redSliceLogic.GetSliceNode()
    self.yellowSliceNode=self.yellowSliceLogic.GetSliceNode()
    self.currentFOVRed = []
    self.currentFOVYellow = []

    self.createPatientWatchBox()
    self.createTabWidget()

    #
    # Step 1: Data Selection
    #

    # Layout within a row of that section

    firstRow = qt.QWidget()
    rowLayout=qt.QHBoxLayout()
    alignment=qt.Qt.AlignLeft
    rowLayout.setAlignment(alignment)
    firstRow.setLayout(rowLayout)
    rowLayout.setDirection(0)

    self.text=qt.QLabel('Choose Patient ID:      ')
    rowLayout.addWidget(self.text)

    # Create PatientSelector
    self.patientSelector=ctk.ctkComboBox()
    self.patientSelector.setFixedWidth(200)
    rowLayout.addWidget(self.patientSelector)

    # Update PatientSelector Button
    refreshPixmap=qt.QPixmap(self.modulePath+ 'Resources/Icons/icon-update.png')
    refreshIcon=qt.QIcon(refreshPixmap)
    self.updatePatientListButton = qt.QPushButton("Refresh Patient List")
    self.updatePatientListButton.setFixedHeight(25)
    self.updatePatientListButton.setIcon(refreshIcon)
    rowLayout.addWidget(self.updatePatientListButton)

    # Info Box Data selection
    self.helperLabel=qt.QLabel()
    helperPixmap = qt.QPixmap(self.modulePath+ 'Resources/Icons/icon-infoBox.png')
    self.helperLabel.setPixmap(helperPixmap)
    self.helperLabel.setToolTip('Start by selecting the patient. Then choose your preop directory, containing the '
                                'T2-image volume and a segmentation. Finally select your intraop directory where '
                                'the DICOM-files are incoming. Click load and segment once a series showd up that'
                                ' needs to get segmented.')

    rowLayout.addWidget(self.helperLabel)
    self.dataSelectionGroupBoxLayout.addRow(firstRow)

    # Folder Button
    folderPixmap=qt.QPixmap(self.modulePath+ 'Resources/Icons/icon-folder.png')
    folderIcon=qt.QIcon(folderPixmap)

    # Preop Directory Button
    self.preopDirButton = qt.QPushButton('choose directory')
    self.preopDirButton.setIcon(folderIcon)
    self.dataSelectionGroupBoxLayout.addRow("Select preop directory:", self.preopDirButton)

    # Series Selector
    self.preopSegmentationSelector = ctk.ctkCollapsibleGroupBox()
    self.preopSegmentationSelector.setTitle("Preop Segmentations")
    self.preopSegmentationSelector.collapsed= True
    self.preopSegmentationSelector.collapsedHeight=60
    self.preopSegmentationSelector.hide()
    self.dataSelectionGroupBoxLayout.addRow(self.preopSegmentationSelector)
    preopSegmentationSelectorLayout = qt.QFormLayout(self.preopSegmentationSelector)

    # create ListView for intraop series selection
    self.seriesViewPreop = qt.QListView()
    self.seriesViewPreop.setObjectName('SeriesTable')
    self.seriesViewPreop.setSpacing(3)
    self.seriesModelPreop = qt.QStandardItemModel()
    self.seriesModelPreop.setHorizontalHeaderLabels(['Series ID'])
    self.seriesViewPreop.setModel(self.seriesModelPreop)
    self.seriesViewPreop.setSelectionMode(qt.QAbstractItemView.ExtendedSelection)
    self.seriesViewPreop.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
    preopSegmentationSelectorLayout.addWidget(self.seriesViewPreop)

    row = qt.QWidget()
    rowLayout=qt.QHBoxLayout()
    alignment=qt.Qt.AlignRight
    rowLayout.setAlignment(alignment)
    row.setLayout(rowLayout)
    rowLayout.setDirection(0)

    # Intraop Directory Button
    self.selectSegmentationsButton = qt.QPushButton('Load Segmentation(s)')
    self.selectSegmentationsButton.setEnabled(False)
    self.selectSegmentationsButton.hide()
    rowLayout.addWidget(self.selectSegmentationsButton)

    # Intraop Directory Button
    self.createFiducialsButton = qt.QPushButton('Create Fiducials')
    self.createFiducialsButton.setEnabled(False)
    self.createFiducialsButton.hide()
    rowLayout.addWidget(self.createFiducialsButton)

    self.dataSelectionGroupBoxLayout.addRow(row)

    # Intraop Directory Button
    self.intraopDirButton = qt.QPushButton('choose directory')
    self.intraopDirButton.setIcon(folderIcon)
    self.intraopDirButton.setEnabled(0)
    self.dataSelectionGroupBoxLayout.addRow("Select intraop directory:", self.intraopDirButton)

    # add buffer line
    self.layout.addStretch(1)

    # Series Selector
    self.intraopSeriesSelector = ctk.ctkCollapsibleGroupBox()
    self.intraopSeriesSelector.setTitle("Intraop series")
    self.intraopSeriesSelector.collapsed= True
    self.dataSelectionGroupBoxLayout.addRow(self.intraopSeriesSelector)
    intraopSeriesSelectorLayout = qt.QFormLayout(self.intraopSeriesSelector)

    # create ListView for intraop series selection
    self.seriesView = qt.QListView()
    self.seriesView.setObjectName('SeriesTable')
    self.seriesView.setSpacing(3)
    self.seriesModel = qt.QStandardItemModel()
    self.seriesModel.setHorizontalHeaderLabels(['Series ID'])
    self.seriesView.setModel(self.seriesModel)
    self.seriesView.setSelectionMode(qt.QAbstractItemView.ExtendedSelection)
    self.seriesView.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
    intraopSeriesSelectorLayout.addWidget(self.seriesView)

    row = qt.QWidget()
    rowLayout=qt.QHBoxLayout()
    alignment=qt.Qt.AlignRight
    rowLayout.setAlignment(alignment)
    row.setLayout(rowLayout)
    rowLayout.setDirection(0)

    # Load Series into Slicer Button
    self.loadIntraopDataButton = qt.QPushButton("Load and Segment")
    self.loadIntraopDataButton.toolTip = "Load and Segment"
    self.loadIntraopDataButton.enabled = False
    rowLayout.addWidget(self.loadIntraopDataButton)

    self.createIncomeSimulationButtons()

    # load Data using PCampReview folder structure
    self.reRegButton = qt.QPushButton("Re-Registration")
    self.reRegButton.toolTip = "Re-Registration"
    self.reRegButton.enabled = False
    self.reRegButton.setStyleSheet(self.STYLE_WHITE_BACKGROUND)
    rowLayout.addWidget(self.reRegButton)
    self.dataSelectionGroupBoxLayout.addWidget(row)

    # load Data using PCampReview folder structure
    self.loadDataPCAMPButton = qt.QPushButton("loadDataPCAMPButton")
    self.loadDataPCAMPButton.toolTip = "loadDataPCAMPButton"
    self.loadDataPCAMPButton.enabled = True
    self.loadDataPCAMPButton.setStyleSheet(self.STYLE_WHITE_BACKGROUND)
    self.loadDataPCAMPButton.hide()
    self.dataSelectionGroupBoxLayout.addWidget(self.loadDataPCAMPButton)

    # _____________________________________________________________________________________________________ #

    #
    # Step 2: Label Selection
    #
    self.labelSelectionCollapsibleButton = ctk.ctkCollapsibleButton()
    self.labelSelectionCollapsibleButton.text = "Step 2: Label Selection"
    self.labelSelectionCollapsibleButton.collapsed=0
    self.labelSelectionCollapsibleButton.hide()
    self.layout.addWidget(self.labelSelectionCollapsibleButton)

    firstRow = qt.QWidget()
    rowLayout=qt.QHBoxLayout()
    firstRow.setLayout(rowLayout)

    self.text=qt.QLabel('Reference Volume: ')
    rowLayout.addWidget(self.text)

    # reference volume selector
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
    rowLayout.addWidget(self.referenceVolumeSelector)
    # set info box

    self.helperLabel=qt.QLabel()
    helperPixmap = qt.QPixmap('/Users/peterbehringer/MyDevelopment/Icons/icon-infoBox.png')
    qSize=qt.QSize(20,20)
    helperPixmap=helperPixmap.scaled(qSize)
    self.helperLabel.setPixmap(helperPixmap)
    self.helperLabel.setToolTip('This is the information you needed, right?')

    rowLayout.addWidget(self.helperLabel)

    self.labelSelectionGroupBoxLayout.addRow(firstRow)

    # Set Icon Size for the 4 Icon Items
    size=qt.QSize(40,40)

    # Create Quick Segmentation Button
    pixmap=qt.QPixmap(self.modulePath +  'Resources/Icons/icon-quickSegmentation.png')
    icon=qt.QIcon(pixmap)
    self.startQuickSegmentationButton=qt.QPushButton('Quick Mode')
    self.startQuickSegmentationButton.setIcon(icon)
    self.startQuickSegmentationButton.setIconSize(size)
    self.startQuickSegmentationButton.setFixedHeight(50)
    # self.startQuickSegmentationButton.setFixedWidth(120)
    self.startQuickSegmentationButton.setStyleSheet(self.STYLE_WHITE_BACKGROUND)

    # Create Label Segmentation Button
    pixmap=qt.QPixmap(self.modulePath +  'Resources/Icons/icon-labelSegmentation.png')
    icon=qt.QIcon(pixmap)
    self.startLabelSegmentationButton=qt.QPushButton('Label Mode')
    self.startLabelSegmentationButton.setIcon(icon)
    self.startLabelSegmentationButton.setIconSize(size)
    self.startLabelSegmentationButton.setFixedHeight(50)
    # self.startLabelSegmentationButton.setFixedWidth(120)
    self.startLabelSegmentationButton.setStyleSheet(self.STYLE_WHITE_BACKGROUND)

    # Create Apply Segmentation Button
    pixmap=qt.QPixmap(self.modulePath +  'Resources/Icons/icon-applySegmentation.png')
    icon=qt.QIcon(pixmap)
    self.applySegmentationButton=qt.QPushButton()
    self.applySegmentationButton.setIcon(icon)
    self.applySegmentationButton.setIconSize(size)
    self.applySegmentationButton.setFixedHeight(50)
    # self.applySegmentationButton.setFixedWidth(70)
    self.applySegmentationButton.setStyleSheet(self.STYLE_WHITE_BACKGROUND)
    self.applySegmentationButton.setEnabled(0)

    self.forwardButton=qt.QPushButton('Step forward')
    self.forwardButton.setFixedHeight(50)

    self.backButton=qt.QPushButton('Step back')
    self.backButton.setFixedHeight(50)

    self.deactivateUndoRedoButtons()

    # Create ButtonBox to fill in those Buttons
    buttonBox1=qt.QDialogButtonBox()
    buttonBox1.setLayoutDirection(1)
    buttonBox1.centerButtons=False

    buttonBox1.addButton(self.forwardButton,buttonBox1.ActionRole)
    buttonBox1.addButton(self.backButton,buttonBox1.ActionRole)
    buttonBox1.addButton(self.applySegmentationButton,buttonBox1.ActionRole)
    buttonBox1.addButton(self.startQuickSegmentationButton,buttonBox1.ActionRole)
    buttonBox1.addButton(self.startLabelSegmentationButton,buttonBox1.ActionRole)

    self.labelSelectionGroupBoxLayout.addWidget(buttonBox1)

    # Editor Widget
    editorWidgetParent = slicer.qMRMLWidget()
    editorWidgetParent.setLayout(qt.QVBoxLayout())
    editorWidgetParent.setMRMLScene(slicer.mrmlScene)

    self.editUtil = EditorLib.EditUtil.EditUtil()
    self.editorWidget = EditorWidget(parent=editorWidgetParent,showVolumesFrame=False)
    self.editorWidget.setup()
    self.editorParameterNode = self.editUtil.getParameterNode()
    self.labelSelectionGroupBoxLayout.addRow(editorWidgetParent)

    #
    # Step 3: Registration
    #

    # preop volume selector
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
    self.registrationGroupBoxLayout.addRow("Preop Image Volume: ", self.preopVolumeSelector)

    # preop label selector
    self.preopLabelSelector = slicer.qMRMLNodeComboBox()
    self.preopLabelSelector.nodeTypes = ( ("vtkMRMLScalarVolumeNode"), "" )
    self.preopLabelSelector.addAttribute( "vtkMRMLScalarVolumeNode", "LabelMap", 1 )
    self.preopLabelSelector.selectNodeUponCreation = False
    self.preopLabelSelector.addEnabled = False
    self.preopLabelSelector.removeEnabled = False
    self.preopLabelSelector.noneEnabled = False
    self.preopLabelSelector.showHidden = False
    self.preopLabelSelector.showChildNodeTypes = False
    self.preopLabelSelector.setMRMLScene( slicer.mrmlScene )
    self.preopLabelSelector.setToolTip( "Pick the input to the algorithm." )
    self.registrationGroupBoxLayout.addRow("Preop Label Volume: ", self.preopLabelSelector)

    # intraop volume selector
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
    self.registrationGroupBoxLayout.addRow("Intraop Image Volume: ", self.intraopVolumeSelector)

    # intraop label selector
    self.intraopLabelSelector = slicer.qMRMLNodeComboBox()
    self.intraopLabelSelector.nodeTypes = ( ("vtkMRMLScalarVolumeNode"), "" )
    self.intraopLabelSelector.addAttribute( "vtkMRMLScalarVolumeNode", "LabelMap", 1 )
    self.intraopLabelSelector.selectNodeUponCreation = True
    self.intraopLabelSelector.addEnabled = False
    self.intraopLabelSelector.removeEnabled = False
    self.intraopLabelSelector.noneEnabled = False
    self.intraopLabelSelector.showHidden = False
    self.intraopLabelSelector.showChildNodeTypes = False
    self.intraopLabelSelector.setMRMLScene( slicer.mrmlScene )
    self.intraopLabelSelector.setToolTip( "Pick the input to the algorithm." )
    self.registrationGroupBoxLayout.addRow("Intraop Label Volume: ", self.intraopLabelSelector)

    # target selector
    self.fiducialSelector = slicer.qMRMLNodeComboBox()
    self.fiducialSelector.nodeTypes = ( ("vtkMRMLMarkupsFiducialNode"), "" )
    self.fiducialSelector.selectNodeUponCreation = False
    self.fiducialSelector.addEnabled = False
    self.fiducialSelector.removeEnabled = False
    self.fiducialSelector.noneEnabled = True
    self.fiducialSelector.showHidden = False
    self.fiducialSelector.showChildNodeTypes = False
    self.fiducialSelector.setMRMLScene( slicer.mrmlScene )
    self.fiducialSelector.setToolTip( "Select the Targets" )
    self.registrationGroupBoxLayout.addRow("Targets: ", self.fiducialSelector)

    # Apply Registration Button
    greenCheckPixmap=qt.QPixmap(self.modulePath +  'Resources/Icons/icon-greenCheck.png')
    greenCheckIcon=qt.QIcon(greenCheckPixmap)
    self.applyBSplineRegistrationButton = qt.QPushButton("Apply Registration")
    self.applyBSplineRegistrationButton.setIcon(greenCheckIcon)
    self.applyBSplineRegistrationButton.toolTip = "Run the algorithm."
    self.applyBSplineRegistrationButton.enabled = True
    self.applyBSplineRegistrationButton.setFixedHeight(45)
    self.registrationGroupBoxLayout.addRow(self.applyBSplineRegistrationButton)

    #
    # Step 4: Registration Evaluation
    #

    # Buttons which registration step should be shown
    selectPatientRowLayout = qt.QHBoxLayout()

    firstRow = qt.QWidget()
    rowLayout=qt.QHBoxLayout()
    alignment=qt.Qt.AlignLeft
    rowLayout.setAlignment(alignment)
    firstRow.setLayout(rowLayout)
    rowLayout.setDirection(0)

    self.text=qt.QLabel('Registration Result')
    rowLayout.addWidget(self.text)

    # Create PatientSelector
    self.resultSelector=ctk.ctkComboBox()
    self.resultSelector.setFixedWidth(250)
    rowLayout.addWidget(self.resultSelector)

    self.showPreopButton=qt.QPushButton('Show Preop')
    self.showRigidButton=qt.QPushButton('Show Rigid Result')
    self.showAffineButton=qt.QPushButton('Show Affine Result')
    self.showBSplineButton=qt.QPushButton('Show BSpline Result')

    biggerWidget=qt.QWidget()
    twoRowLayout=qt.QVBoxLayout()
    biggerWidget.setLayout(twoRowLayout)

    twoRowLayout.addWidget(firstRow)

    secondRow=qt.QWidget()
    rowLayout=qt.QHBoxLayout()
    secondRow.setLayout(rowLayout)
    rowLayout.addWidget(self.showPreopButton)
    rowLayout.addWidget(self.showRigidButton)
    rowLayout.addWidget(self.showAffineButton)
    rowLayout.addWidget(self.showBSplineButton)
    twoRowLayout.addWidget(secondRow)

    selectPatientRowLayout.addWidget(biggerWidget)

    self.groupBoxDisplay = qt.QGroupBox("Display")
    self.groupBoxDisplayLayout = qt.QFormLayout(self.groupBoxDisplay)
    self.groupBoxDisplayLayout.addRow(selectPatientRowLayout)
    self.evaluationGroupBoxLayout.addWidget(self.groupBoxDisplay)

    # fadeSlider
    fadeHolder = qt.QWidget()
    fadeLayout = qt.QHBoxLayout()
    fadeHolder.setLayout(fadeLayout)

    self.groupBox = qt.QGroupBox("Visual Evaluation")
    self.groupBoxLayout = qt.QFormLayout(self.groupBox)
    self.evaluationGroupBoxLayout.addWidget(self.groupBox)

    self.fadeSlider = ctk.ctkSliderWidget()
    self.fadeSlider.minimum = 0
    self.fadeSlider.maximum = 1.0
    self.fadeSlider.value = 0
    self.fadeSlider.singleStep = 0.05
    fadeLayout.addWidget(self.fadeSlider)

    # Rock and Flicker
    animaHolder = qt.QWidget()
    animaLayout = qt.QVBoxLayout()
    animaHolder.setLayout(animaLayout)
    fadeLayout.addWidget(animaHolder)

    self.rockCheckBox = qt.QCheckBox("Rock")
    self.rockCheckBox.checked = False
    animaLayout.addWidget(self.rockCheckBox)

    # Flicker
    self.flickerCheckBox = qt.QCheckBox("Flicker")
    self.flickerCheckBox.checked = False
    animaLayout.addWidget(self.flickerCheckBox)

    self.groupBoxLayout.addRow("Opacity", fadeHolder)

    self.revealCursorCheckBox = qt.QCheckBox("Use RevealCursor")
    self.revealCursorCheckBox.checked = False
    self.groupBoxLayout.addRow("",self.revealCursorCheckBox)

    self.groupBoxTargets = qt.QGroupBox("Targets")
    self.groupBoxLayoutTargets = qt.QFormLayout(self.groupBoxTargets)
    self.evaluationGroupBoxLayout.addWidget(self.groupBoxTargets)

    self.targetTable=qt.QTableWidget()
    self.targetTable.setRowCount(0)
    self.targetTable.setColumnCount(3)
    self.targetTable.setColumnWidth(0,160)
    self.targetTable.setColumnWidth(1,180)
    self.targetTable.setColumnWidth(2,180)
    self.targetTable.setHorizontalHeaderLabels(['Target','Distance to needle-tip 2D [mm]','Distance to needle-tip 3D [mm]'])

    self.groupBoxLayoutTargets.addRow(self.targetTable)

    self.needleTipButton=qt.QPushButton('Set needle-tip')
    self.groupBoxLayoutTargets.addRow(self.needleTipButton)

    self.groupBoxOutputData = qt.QGroupBox("Data output")
    self.groupBoxOutputDataLayout = qt.QFormLayout(self.groupBoxOutputData)
    # self.groupBoxDisplayLayout.addRow(selectPatientRowLayout)
    self.evaluationGroupBoxLayout.addWidget(self.groupBoxOutputData)

    # Output Directory Button
    self.outputDirButton = qt.QPushButton(self.shortenDirText(str(self.settings.value('RegistrationModule/OutputLocation'))))
    self.outputDirButton.setIcon(folderIcon)
    self.groupBoxOutputDataLayout.addRow("Select costum output directory:", self.outputDirButton)

    # Save Data Button
    littleDiscPixmap=qt.QPixmap(self.modulePath +  'Resources/Icons/icon-littleDisc.png')
    littleDiscIcon=qt.QIcon(littleDiscPixmap)
    self.saveDataButton=qt.QPushButton('Save Data')
    self.saveDataButton.setMaximumWidth(150)
    self.saveDataButton.setIcon(littleDiscIcon)
    self.groupBoxOutputDataLayout.addWidget(self.saveDataButton)

    self.setupConnections()

   # _____________________________________________________________________________________________________ #

    # set initial layout
    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutSideBySideView)

    # set slice views to axial
    self.redSliceNode.SetOrientationToAxial()
    self.yellowSliceNode.SetOrientationToAxial()

    # initially, set Evaluation Section disabled TODO: set False again
    self.tabBar.setTabEnabled(1,False)
    self.tabBar.setTabEnabled(2,False)
    self.tabBar.setTabEnabled(3,False)

    # enter Module on Tab 1
    self.onTab1clicked()

    # set up color table
    self.logic.setupColorTable()

    self.removeSliceAnnotations()
    self.updatePatientSelector()

  def setupConnections(self):
    self.tabWidget.connect('currentChanged(int)',self.onTabWidgetClicked)
    self.patientSelector.connect('currentIndexChanged(int)',self.updatePatientViewBox)
    self.updatePatientListButton.connect('clicked(bool)',self.updatePatientSelector)
    self.selectSegmentationsButton.connect('clicked()', self.onSelectSegmentationsButtonClicked)
    self.preopDirButton.connect('clicked()', self.onPreopDirSelected)
    self.createFiducialsButton.connect('clicked()', self.onIntraopDirSelected)
    self.intraopDirButton.connect('clicked()', self.onIntraopDirSelected)
    self.reRegButton.connect('clicked(bool)',self.onReRegistrationClicked)
    self.loadDataPCAMPButton.connect('clicked(bool)',self.loadDataPCAMPStyle)
    self.referenceVolumeSelector.connect('currentNodeChanged(bool)',self.onTab2clicked)
    self.forwardButton.connect('clicked(bool)',self.onForwardButton)
    self.backButton.connect('clicked(bool)',self.onBackButton)
    self.applyBSplineRegistrationButton.connect('clicked(bool)',self.onApplyRegistrationClicked)
    self.resultSelector.connect('currentIndexChanged(int)',self.updateRegistrationResult)
    self.showPreopButton.connect('clicked(bool)',self.onPreopCheckBoxClicked)
    self.showRigidButton.connect('clicked(bool)',self.onRigidCheckBoxClicked)
    self.showAffineButton.connect('clicked(bool)',self.onAffineCheckBoxClicked)
    self.showBSplineButton.connect('clicked(bool)',self.onBSplineCheckBoxClicked)
    self.fadeSlider.connect('valueChanged(double)', self.changeOpacity)
    self.rockCheckBox.connect('toggled(bool)', self.onRockToggled)
    self.flickerCheckBox.connect('toggled(bool)', self.onFlickerToggled)
    self.revealCursorCheckBox.connect('toggled(bool)', self.revealToggled)
    self.needleTipButton.connect('clicked(bool)',self.onNeedleTipButtonClicked)
    self.outputDirButton.connect('clicked()', self.onOutputDirSelected)
    self.startQuickSegmentationButton.connect('clicked(bool)',self.onStartSegmentationButton)
    self.startLabelSegmentationButton.connect('clicked(bool)',self.onStartLabelSegmentationButton)
    self.applySegmentationButton.connect('clicked(bool)',self.onApplySegmentationButton)
    self.loadIntraopDataButton.connect('clicked(bool)',self.onloadIntraopDataButtonClicked)
    self.preopVolumeSelector.connect('currentNodeChanged(bool)',self.onTab3clicked)
    self.intraopVolumeSelector.connect('currentNodeChanged(bool)',self.onTab3clicked)
    self.intraopLabelSelector.connect('currentNodeChanged(bool)',self.onTab3clicked)
    self.preopLabelSelector.connect('currentNodeChanged(bool)',self.onTab3clicked)
    self.fiducialSelector.connect('currentNodeChanged(bool)',self.onTab3clicked)
    self.dicomDatabase.patientAdded.connect(self.updatePatientSelector)

  def cleanup(self):
    ScriptedLoadableModuleWidget.cleanup(self)
    self.dicomDatabase.patientAdded.disconnect(self.updatePatientSelector)

  def deactivateUndoRedoButtons(self):
    self.forwardButton.setEnabled(0)
    self.backButton.setEnabled(0)

  def updateUndoRedoButtons(self, observer=None, caller=None):
    self.updateBackButton()
    self.updateForwardButton()

  def updateBackButton(self):
    activeFiducials=slicer.mrmlScene.GetNodesByName('inputMarkupNode').GetItemAsObject(0)
    if activeFiducials.GetNumberOfFiducials() > 0:
      self.backButton.setEnabled(1)
    else:
      self.backButton.setEnabled(0)

  def updateForwardButton(self):
    if self.deletedMarkups.GetNumberOfFiducials() > 0:
      self.forwardButton.setEnabled(1)
    else:
      self.forwardButton.setEnabled(0)

  def startStoreSCP(self):

    # command : $ sudo storescp -v -p 104
    pathToExe=(slicer.app.slicerHome+'/bin/storescp')
    port=104
    cmd=('sudo '+pathToExe+ ' -v -p '+str(port))
    os.system(cmd)

  def onloadIntraopDataButtonClicked(self):

    selectedSeriesList=self.getSelectedSeriesFromSelector()
    directory = self.intraopDataDir

    if self.intraopDataDir:
      self.currentIntraopVolume=self.logic.loadSeriesIntoSlicer(selectedSeriesList,directory)

      # set last inputVolume Node as Reference Volume in Label Selection
      self.referenceVolumeSelector.setCurrentNode(self.currentIntraopVolume)

      # set last inputVolume Node as Intraop Image Volume in Registration
      self.intraopVolumeSelector.setCurrentNode(self.currentIntraopVolume)

      # Fit Volume To Screen
      slicer.app.applicationLogic().FitSliceToAll()

      # Allow PatientSelector to be updated
      self.updatePatientSelectorFlag = True

      # uncheck loaded items in the Intrap series selection
      for item in range(len(self.logic.seriesList)):
        self.seriesModel.item(item).setCheckState(0)

      # set Tab enabled
      self.tabBar.setTabEnabled(1,True)

      # enter Label Selection Section
      self.onTab2clicked()

  def updateRegistrationResult(self):

    # distinguish between rigid and BSpline result
    currentItem = self.resultSelector.currentText

    # get index
    for index in range(len(self.registrationResults)):
      self.markupsLogic.SetAllMarkupsVisibility(self.registrationResults[index]['outputTargetsRigid'],False)
      self.markupsLogic.SetAllMarkupsVisibility(self.registrationResults[index]['outputTargetsAffine'],False)
      self.markupsLogic.SetAllMarkupsVisibility(self.registrationResults[index]['outputTargetsBSpline'],False)

      if self.registrationResults[index]['name'] == currentItem:
        self.currentRegistrationResult=index


    # set variables needed by on xx clicked
    self.currentIntraopVolume=self.registrationResults[index]['fixedVolume']
    self.outputVolumeRigid=self.registrationResults[index]['outputVolumeRigid']
    self.outputVolumeAffine=self.registrationResults[index]['outputVolumeAffine']
    self.outputVolumeBSpline=self.registrationResults[index]['outputVolumeBSpline']
    self.outputTargetsRigid=self.registrationResults[index]['outputTargetsRigid']
    self.outputTargetsAffine=self.registrationResults[index]['outputTargetsAffine']
    self.outputTargetsBSpline=self.registrationResults[index]['outputTargetsBSpline']
    self.preopVolume=self.registrationResults[index]['movingVolume']

    # update GUI
    self.onRigidCheckBoxClicked()

  def updateRegistrationResultSelector(self):

    itemlist=[]

    # get the items
    for result in range(len(self.registrationResults)):
      itemlist.append(self.registrationResults[result]['name'])

    # update the selector
    for item in itemlist:
      if item not in self.selectableRegistrationResults:
        self.selectableRegistrationResults.append(item)
        self.resultSelector.addItem(item)
        index = self.resultSelector.findText(item)
        self.resultSelector.currentIndex = index

  def onSelectSegmentationsButtonClicked(self):
    return True

  def onReRegistrationClicked(self):
    print ('performing reregistration')

    index=len(self.registrationResults)-1

    # fixed volume: current intraop volume
    selectedSeriesList=self.getSelectedSeriesFromSelector()
    directory = self.intraopDataDir
    self.currentIntraopVolume=self.logic.loadSeriesIntoSlicer(selectedSeriesList, directory)

    # moving volume: copy last fixed volume
    sourceVolumeNode = self.registrationResults[0]['fixedVolume']
    volumesLogic = slicer.modules.volumes.logic()
    movingVolume = volumesLogic.CloneVolume(slicer.mrmlScene, sourceVolumeNode, 'movingVolumeReReg')
    movingLabel=None

    # get the intraop targets
    targets=self.registrationResults[0]['outputTargetsBSpline']

    # take the 'intraop label map', which is always fixed label in the very first preop-intraop registration
    originalFixedLabel=self.registrationResults[0]['fixedLabel']

    # create fixed label
    volumesLogic = slicer.modules.volumes.logic()
    fixedLabel = volumesLogic.CreateAndAddLabelVolume(slicer.mrmlScene,self.currentIntraopVolume,
                                                      self.currentIntraopVolume.GetName()+'-label')

    if index==0:
      print 'will resample label with same mask'
      # last registration was preop-intraop, take the same mask
      # this is an identity transform:
      lastRigidTfm=vtk.vtkGeneralTransform()
      lastRigidTfm.Identity()
      self.logic.BRAINSResample(inputVolume=originalFixedLabel,referenceVolume=self.currentIntraopVolume,
                                outputVolume=fixedLabel,warpTransform=lastRigidTfm)

    else:
      lastRigidTfm = self.registrationResults[index]['outputTransformRigid']
      self.logic.BRAINSResample(inputVolume=originalFixedLabel,referenceVolume=self.currentIntraopVolume,
                                outputVolume=fixedLabel,warpTransform=lastRigidTfm)

    reRegOutput = self.logic.applyReRegistration(fixedVolume=self.currentIntraopVolume,movingVolume=movingVolume,
                                                 fixedLabel=fixedLabel,targets=targets,lastRigidTfm=lastRigidTfm)

    # create registration output dictionary
    params=[]
    params.append(sourceVolumeNode)
    params.append(self.currentIntraopVolume)
    params.append(movingLabel)
    params.append(fixedLabel)
    params.append(targets)

    name = str(self.currentIntraopVolume.GetName())
    self.createRegistrationResult(name,params,reRegOutput)

    self.outputVolumeRigid=reRegOutput[0]
    self.outputVolumeAffine=reRegOutput[1]
    self.outputVolumeBSpline=reRegOutput[2]
    self.outputTransformRigid=reRegOutput[3]
    self.outputTransformAffine=reRegOutput[4]
    self.outputTransformBSpline=reRegOutput[5]
    self.outputTargetsRigid=reRegOutput[6][0]
    self.outputTargetsAffine=reRegOutput[6][1]
    self.outputTargetsBSpline=reRegOutput[6][2]

    slicer.mrmlScene.AddNode(self.outputTargetsRigid)
    slicer.mrmlScene.AddNode(self.outputTargetsAffine)
    slicer.mrmlScene.AddNode(self.outputTargetsBSpline)

    # set up screens
    self.setupScreenAfterRegistration()

    # update the combo box
    self.updateRegistrationResultSelector()

    # select BSpline view
    self.onBSplineCheckBoxClicked()

    print ('Re-Registration Function is done')

  def loadDataPCAMPStyle(self):
    logging.info("loadDataPCAMPStyle")
    testpath = '/Users/peterbehringer/MyImageData/preprocessed_data/'
    self.selectedStudyName = 'QIN-PROSTATE-01-0025_19711123_1504'

    inputDir = testpath
    self.resourcesDir = os.path.join(inputDir,self.selectedStudyName,'RESOURCES')

    # expect one directory for each processed series, with the name
    # corresponding to the series number
    self.seriesMap = {}

    for root,subdirs,files in os.walk(self.resourcesDir):
      print('Root: '+root+', files: '+str(files))
      resourceType = os.path.split(root)[1]

      print('Resource: '+resourceType)

      if resourceType == 'Reconstructions':
        for f in files:
          print('File: '+f)
          if f.endswith('.xml'):
            metaFile = os.path.join(root,f)
            print('Ends with xml: '+metaFile)
            try:
              (seriesNumber,seriesName) = self.getSeriesInfoFromXML(metaFile)
              print(str(seriesNumber)+' '+seriesName)
            except:
              print('Failed to get from XML')
              continue

            volumePath = os.path.join(root,seriesNumber+'.nrrd')
            self.seriesMap[seriesNumber] = {'MetaInfo':None, 'NRRDLocation':volumePath,'LongName':seriesName}
            self.seriesMap[seriesNumber]['ShortName'] = str(seriesNumber)+":"+seriesName

    print('All series found: '+str(self.seriesMap.keys()))
    print('All series found: '+str(self.seriesMap.values()))

    print ('******************************************************************************')

    self.preopImagePath=''
    self.preopSegmentationPath=''
    self.preopSegmentations=[]

    for series in self.seriesMap:
      seriesName=str(self.seriesMap[series]['LongName'])
      print ('series Number '+series + ' ' + seriesName)
      if "AX" in str(seriesName) and "T2" in str(seriesName):
        print (' FOUND THE SERIES OF INTEREST, ITS '+seriesName)
        print (' LOCATION OF VOLUME : ' +str(self.seriesMap[series]['NRRDLocation']))

        path = os.path.join(self.seriesMap[series]['NRRDLocation'])
        print (' LOCATION OF IMAGE path : '+str(path))

        segmentationPath= os.path.dirname(os.path.dirname(path))
        segmentationPath = (str(segmentationPath) + '/Segmentations')
        print (' LOCATION OF SEGMENTATION path : '+str(segmentationPath))

        self.preopImagePath=self.seriesMap[series]['NRRDLocation']
        self.preopSegmentationPath=segmentationPath

        self.preopSegmentations=os.listdir(segmentationPath)

        print str(self.preopSegmentations)

        break

    self.updatePreopSegmentationTable(self.preopSegmentations)

  def getSeriesInfoFromXML(self, f):
    import xml.dom.minidom
    dom = xml.dom.minidom.parse(f)
    number = self.findElement(dom, 'SeriesNumber')
    name = self.findElement(dom, 'SeriesDescription')
    name = name.replace('-','')
    name = name.replace('(','')
    name = name.replace(')','')
    return number,name

  def findElement(self, dom, name):
    els = dom.getElementsByTagName('element')
    for e in els:
      if e.getAttribute('name') == name:
        return e.childNodes[0].nodeValue

  def clearTargetTable(self):

    self.needleTipButton.enabled=False

    self.targetTable.clear()
    self.targetTable.setColumnCount(3)
    self.targetTable.setColumnWidth(0,180)
    self.targetTable.setColumnWidth(1,200)
    self.targetTable.setColumnWidth(2,200)
    self.targetTable.setHorizontalHeaderLabels(['Target','Distance to needle-tip 2D [mm]',
                                                'Distance to needle-tip 3D [mm]'])

  def onNeedleTipButtonClicked(self):
    self.needleTipButton.enabled=False
    self.logic.setNeedleTipPosition()

  def updateTargetTable(self,observer,caller):

    self.needleTip_position=[]
    self.target_positions=[]

    # get the positions of needle Tip and Targets
    [self.needleTip_position,self.target_positions]=self.logic.getNeedleTipAndTargetsPositions()

    # get the targets
    fidNode1=slicer.mrmlScene.GetNodesByName('targets-BSPLINE').GetItemAsObject(0)
    number_of_targets=fidNode1.GetNumberOfFiducials()

    # set number of rows in targetTable
    self.targetTable.setRowCount(number_of_targets)
    self.target_items=[]

    # refresh the targetTable
    for target in range(number_of_targets):
      target_text=fidNode1.GetNthFiducialLabel(target)
      item=qt.QTableWidgetItem(target_text)
      self.targetTable.setItem(target,0,item)
      # make sure to keep a reference to the item
      self.target_items.append(item)

    self.items_2D=[]
    self.items_3D=[]

    for index in range(number_of_targets):
      distances=self.logic.measureDistance(self.target_positions[index],self.needleTip_position)
      text_for_2D_column=('x = '+str(round(distances[0],2))+' y = '+str(round(distances[1],2)))
      text_for_3D_colomn=str(round(distances[3],2))

      item_2D=qt.QTableWidgetItem(text_for_2D_column)
      self.targetTable.setItem(index,1,item_2D)
      self.items_2D.append(item_2D)
      print str(text_for_2D_column)

      item_3D=qt.QTableWidgetItem(text_for_3D_colomn)
      self.targetTable.setItem(index,2,item_3D)
      self.items_3D.append(item_3D)
      print str(text_for_3D_colomn)

    # reset needleTipButton
    self.needleTipButton.enabled=True

  def removeSliceAnnotations(self):
    try:
      self.red_renderer.RemoveActor(self.text_preop)
      self.yellow_renderer.RemoveActor(self.text_intraop)
      self.redSliceView.update()
      self.yellowSliceView.update()
    except:
      pass

  def addSliceAnnotations(self):

    width = self.redSliceView.width
    renderWindow = self.redSliceView.renderWindow()
    self.red_renderer = renderWindow.GetRenderers().GetItemAsObject(0)

    self.text_preop = vtk.vtkTextActor()
    self.text_preop.SetInput('PREOP')
    textProperty = self.text_preop.GetTextProperty()
    textProperty.SetFontSize(70)
    textProperty.SetColor(1,0,0)
    textProperty.SetBold(1)
    self.text_preop.SetTextProperty(textProperty)

    #TODO: the 90px shift to the left are hard-coded right now, it would be better to
    # take the size of the vtk.vtkTextActor and shift by that size * 0.5
    # BUT -> could not find how to get vtkViewPort from sliceWidget

    self.text_preop.SetDisplayPosition(int(width*0.5-90),50)
    self.red_renderer.AddActor(self.text_preop)
    self.redSliceView.update()


    renderWindow = self.yellowSliceView.renderWindow()
    self.yellow_renderer = renderWindow.GetRenderers().GetItemAsObject(0)

    self.text_intraop = vtk.vtkTextActor()
    self.text_intraop.SetInput('INTRAOP')
    textProperty = self.text_intraop.GetTextProperty()
    textProperty.SetFontSize(70)
    textProperty.SetColor(1,0,0)
    textProperty.SetBold(1)
    self.text_intraop.SetTextProperty(textProperty)
    self.text_intraop.SetDisplayPosition(int(width*0.5-140),50)
    self.yellow_renderer.AddActor(self.text_intraop)
    self.yellowSliceView.update()

  def onForwardButton(self):

    #print ('activeFiducials found')
    numberOfDeletedTargets=self.deletedMarkups.GetNumberOfFiducials()
    print ('numberOfTargets in deletedMarkups is'+str(numberOfDeletedTargets))
    pos=[0.0,0.0,0.0]

    if numberOfDeletedTargets > 0:
      self.deletedMarkups.GetNthFiducialPosition(numberOfDeletedTargets-1,pos)

    print ('deletedMarkups.position = '+str(pos))

    if pos == [0.0,0.0,0.0]:
      print ('pos was 0,0,0 -> go on')
    else:
      activeFiducials=slicer.mrmlScene.GetNodesByName('inputMarkupNode').GetItemAsObject(0)
      activeFiducials.AddFiducialFromArray(pos)

      # delete it in deletedMarkups
      self.deletedMarkups.RemoveMarkup(numberOfDeletedTargets-1)

    self.updateUndoRedoButtons()

  def onBackButton(self):

    # grab the last fiducial of inputMarkupsNode
    activeFiducials=slicer.mrmlScene.GetNodesByName('inputMarkupNode').GetItemAsObject(0)
    #print ('activeFiducials found')
    numberOfTargets=activeFiducials.GetNumberOfFiducials()
    print ('numberOfTargets is'+str(numberOfTargets))
    pos=[0.0,0.0,0.0]
    activeFiducials.GetNthFiducialPosition(numberOfTargets-1,pos)
    print ('activeFiducials.position = '+str(pos))

    if numberOfTargets > 0:
      self.deletedMarkups.GetNthFiducialPosition(numberOfTargets-1,pos)

    activeFiducials.GetNthFiducialPosition(numberOfTargets-1,pos)
    print ('POS BEFORE ENTRY = '+str(pos))
    if pos == [0.0,0.0,0.0]:
      print ('pos was 0,0,0 -> go on')
    else:
      # add it to deletedMarkups
      activeFiducials.GetNthFiducialPosition(numberOfTargets-1,pos)
      #print ('pos = '+str(pos))
      self.deletedMarkups.AddFiducialFromArray(pos)
      print ('added Markup with position '+str(pos)+' to the deletedMarkupsList')
      # delete it in activeFiducials
      activeFiducials.RemoveMarkup(numberOfTargets-1)

    self.updateUndoRedoButtons()

  def revealToggled(self,checked):
    """Turn the RevealCursor on or off
    """
    if self.revealCursor:
      self.revealCursor.tearDown()
    if checked:
      import CompareVolumes
      self.revealCursor = CompareVolumes.LayerReveal()

  def rock(self):
    if not self.rocking:
      self.rockTimer = None
      self.fadeSlider.value = 0.0
    if self.rocking:
      if not self.rockTimer:
        self.rockTimer = qt.QTimer()
        self.rockTimer.start(50)
        self.rockTimer.connect('timeout()', self.rock)
      import math
      self.fadeSlider.value = 0.5 + math.sin(self.rockCount / 10. ) / 2.
      self.rockCount += 1

  def onRockToggled(self,checked):
    self.rocking = checked
    self.rock()

  def flicker(self):
    if not self.flickering:
      self.flickerTimer = None
      self.fadeSlider.value = 0.0
    if self.flickering:
      if not self.flickerTimer:
        if self.fadeSlider.value == 0.5:
          self.fadeSlider.value = 0.25
        self.flickerTimer = qt.QTimer()
        self.flickerTimer.start(300)
        self.flickerTimer.connect('timeout()', self.flicker)
      import math
      self.fadeSlider.value = 1.0 - self.fadeSlider.value

  def onFlickerToggled(self,checked):
    self.flickering = checked
    self.flicker()

  def onPreopDirSelected(self):
    self.preopDataDir = qt.QFileDialog.getExistingDirectory(self.parent,'Preop data directory',
                                                            self.modulePath + '/Resources/Testing/preopDir')
    if os.path.exists(self.preopDataDir):
      self.settings.setValue('RegistrationModule/PreopLocation', self.preopDataDir)
      self.preopDirButton.text = self.shortenDirText(self.preopDataDir)
      self.selectSegmentationsButton.setEnabled(True)
      self.loadPreopData()

  def shortenDirText(self, directory):
    try:
      split=directory.split('/')
      splittedDir=('.../'+str(split[-2])+'/'+str(split[-1]))
      return splittedDir
    except:
      pass

  def onIntraopDirSelected(self):
    self.intraopDataDir = qt.QFileDialog.getExistingDirectory(self.parent,'Intraop data directory',
                                                              self.modulePath + '/Resources/Testing/intraopDir')
    if os.path.exists(self.intraopDataDir):
      self.intraopDirButton.text = self.shortenDirText(self.intraopDataDir)
      self.settings.setValue('RegistrationModule/IntraopLocation', self.intraopDataDir)
      self.logic.initializeListener(self.intraopDataDir)

  def onOutputDirSelected(self):
    self.outputDir = qt.QFileDialog.getExistingDirectory(self.parent,'Preop data directory',
                                                         self.modulePath + '/Resources/Testing/preopDir')
    if os.path.exists(self.outputDir):
      self.outputDirButton.text = self.shortenDirText(self.outputDir)
      self.settings.setValue('RegistrationModule/OutputLocation', self.outputDir)
      self.saveRegistrationOutput()

  def saveRegistrationOutput(self):
    print ('save data .. ')
    return True

  def onTabWidgetClicked(self):
    if self.tabWidget.currentIndex==0:
      self.onTab1clicked()
    if self.tabWidget.currentIndex==1:
      self.onTab2clicked()
    if self.tabWidget.currentIndex==2:
      self.onTab3clicked()
    if self.tabWidget.currentIndex==3:
      self.onTab4clicked()

  def onTab1clicked(self):
    # (re)set the standard Icon
    self.tabBar.setTabIcon(0,self.dataSelectionIcon)
    # removeSliceAnnotations
    self.removeSliceAnnotations()

  def onTab2clicked(self):
    self.tabWidget.setCurrentIndex(1)

    enableButton = 0 if self.referenceVolumeSelector.currentNode() is None else 1
    self.startLabelSegmentationButton.setEnabled(enableButton)
    self.startQuickSegmentationButton.setEnabled(enableButton)

    self.removeSliceAnnotations()

    # set Layout for segmentation
    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)

    # set current reference Volume
    self.compositeNodeRed.SetBackgroundVolumeID(self.currentIntraopVolume.GetID())

    # Fit Volume To Screen
    slicer.app.applicationLogic().FitSliceToAll()

  def onTab3clicked(self):
    self.applyBSplineRegistrationButton.setEnabled(1 if self.inputsAreSet() else 0)

  def inputsAreSet(self):
    return not (self.preopVolumeSelector.currentNode() is None and self.intraopVolumeSelector.currentNode() is None and
            self.preopLabelSelector.currentNode() is None and self.intraopLabelSelector.currentNode() is None and
            self.fiducialSelector.currentNode() is None)

  def onTab4clicked(self):
    self.addSliceAnnotations()

    self.tabBar.setTabEnabled(1,False)
    self.tabBar.setTabEnabled(2,False)

    # enable re-registration function
    self.reRegButton.setEnabled(1)

  def onUpdatePatientListClicked(self):

    self.updatePatientSelectorFlag = True
    self.updatePatientSelector()
    self.updatePatientSelectorFlag = False

  def updatePatientSelector(self):
    logging.info("RegistrationModuleWidget:updatePatientSelector")

    if self.updatePatientSelectorFlag:
      db = self.dicomDatabase
      if db.patients() is None:
        self.patientSelector.addItem('None patient found')

      for patient in db.patients():
        for study in db.studiesForPatient(patient):
          for series in db.seriesForStudy(study):
            for currentFile in db.filesForSeries(series):
               try:
                 if db.fileValue(currentFile,self.PATIENT_NAME) not in self.patientNames:
                   self.patientNames.append(db.fileValue(currentFile,self.PATIENT_NAME))
                 if db.fileValue(currentFile,self.PATIENT_ID) not in self.patientIDs:
                   self.patientIDs.append(db.fileValue(currentFile,self.PATIENT_ID))
                   self.selectablePatientItems.append(db.fileValue(currentFile,self.PATIENT_ID)+' '+
                                                      db.fileValue(currentFile,self.PATIENT_NAME))
                 break
               except:
                 pass
            break
          break

      # add patientNames and patientIDs to patientSelector
      for patient in self.selectablePatientItems:
       if patient not in self.addedPatients:
        self.patientSelector.addItem(patient)
        self.addedPatients.append(patient)
       else:
         pass

    self.intraopDirButton.setEnabled(1)

  def updatePatientViewBox(self):

    if self.patientSelector.currentIndex is not None:

      self.currentPatientName=None
      # get the current index from patientSelector comboBox
      currentIndex=self.patientSelector.currentIndex

      self.currentID=self.patientIDs[currentIndex]

      db = self.dicomDatabase
      currentBirthDateDICOM = None

      # looking for currentPatientName and currentBirthDate
      for patient in db.patients():
        for study in db.studiesForPatient(patient):
          for series in db.seriesForStudy(study):
            for currentFile in db.filesForSeries(series):
               try:
                 if db.fileValue(currentFile,self.PATIENT_ID) == self.currentID:
                   currentPatientNameDICOM= db.fileValue(currentFile,self.PATIENT_NAME)
                   try:
                     currentBirthDateDICOM = db.fileValue(currentFile,self.PATIENT_BIRTH_DATE)
                   except:
                     currentBirthDateDICOM = None
               except:
                 pass

      if currentBirthDateDICOM is None:
        self.patientBirthDate.setText('No Date found')
      else:
        # convert date of birth from 19550112 (yyyymmdd) to 1955-01-12
        currentBirthDateDICOM=str(currentBirthDateDICOM)
        self.currentBirthDate=currentBirthDateDICOM[0:4]+"-"+currentBirthDateDICOM[4:6]+"-"+currentBirthDateDICOM[6:8]

      # convert patient name from XXXX^XXXX to XXXXX, XXXXX
      if "^" in currentPatientNameDICOM:
        length=len(currentPatientNameDICOM)
        index=currentPatientNameDICOM.index('^')
        self.currentPatientName=currentPatientNameDICOM[0:index]+", "+currentPatientNameDICOM[index+1:length]

      # get today date
      self.currentStudyDate=qt.QDate().currentDate()

      # update patientViewBox
      try:
        self.patientBirthDate.setText(self.currentBirthDate)
      except:
        pass
      if self.currentPatientName is not None:
        self.patientName.setText(self.currentPatientName)
      else:
        self.patientName.setText(currentPatientNameDICOM)
        self.currentPatientName=currentPatientNameDICOM
      self.patientID.setText(self.currentID)
      self.studyDate.setText(str(self.currentStudyDate))

  def updateSeriesSelectorTable(self,seriesList):

    # this function updates the series selection table.
    # The function expects the series to be
    # in the order in which the series have been acquired.
    # PROSTATE series needs to be BEFORE the GUIDANCE series,
    # otherwise, the SetCheckState option won't work

    self.seriesModel.clear()
    self.seriesItems = []

    # write items in intraop series selection widget
    for s in range(len(seriesList)):
      seriesText = seriesList[s]
      self.currentSeries=seriesText
      sItem = qt.QStandardItem(seriesText)
      self.seriesItems.append(sItem)
      self.seriesModel.appendRow(sItem)
      sItem.setCheckable(1)

      if "PROSTATE" in seriesText:
        sItem.setCheckState(1)
      if "GUIDANCE" in seriesText:
        sItem.setCheckState(1)
        rowsAboveCurrentItem=int(len(seriesList) - 1)
        for item in range(rowsAboveCurrentItem):
          self.seriesModel.item(item).setCheckState(0)

    # show intraopSeriesTable
    self.intraopSeriesSelector.collapsed=False
    self.loadIntraopDataButton.setEnabled(len(seriesList)>0)

  def updatePreopSegmentationTable(self,seriesList):

    # this function updates the segmentation
    # in the preop segmentation table

    self.seriesModelPreop.clear()
    self.segmentationItems = []

    # write items in intraop series selection widget
    for s in range(len(seriesList)):
      seriesText = seriesList[s]
      self.currentPreopSegmentations=seriesText
      sItem = qt.QStandardItem(seriesText)
      self.segmentationItems.append(sItem)
      self.seriesModelPreop.appendRow(sItem)
      sItem.setCheckable(1)

    # show preop Segmentation Table
    self.preopSegmentationSelector.collapsed = False

  def onPreopCheckBoxClicked(self):

    self.saveCurrentSliceViewPositions()
    self.showPreopButton.setStyleSheet(self.STYLE_GRAY_BACKGROUND_WHITE_FONT)
    self.showRigidButton.setStyleSheet(self.STYLE_WHITE_BACKGROUND)
    self.showAffineButton.setStyleSheet(self.STYLE_WHITE_BACKGROUND)
    self.showBSplineButton.setStyleSheet(self.STYLE_WHITE_BACKGROUND)

    # un-link images
    self.compositeNodeRed.SetLinkedControl(0)
    self.compositNodeYellow.SetLinkedControl(0)

    volumeNode=self.registrationResults[self.currentRegistrationResult]['movingVolume']
    # Get the Volume Node
    #self.compositNodeRed.SetBackgroundVolumeID(slicer.mrmlScene.GetNodesByName('volume-PREOP').GetItemAsObject(0).GetID())
    self.compositeNodeRed.SetBackgroundVolumeID(volumeNode.GetID())

    fiducialNode=self.registrationResults[self.currentRegistrationResult]['targets']

     # show preop Targets
    self.markupsLogic.SetAllMarkupsVisibility(fiducialNode,True)

    # fit slice view
    self.redSliceLogic.FitSliceToAll()

    # zoom in
    fovRed=self.redSliceNode.GetFieldOfView()
    self.redSliceLogic.StartSliceNodeInteraction(2)
    self.redSliceNode.SetFieldOfView(fovRed[0] * 0.5, fovRed[1] * 0.5, fovRed[2])
    self.redSliceLogic.EndSliceNodeInteraction()

    # jump to first markup slice
    self.markupsLogic.JumpSlicesToNthPointInMarkup(fiducialNode.GetID(),1)

    # reset the yellow slice view
    restoredSliceOptions=self.getCurrentSliceViewPositions()
    yellowOffset=restoredSliceOptions[1]
    yellowFOV=restoredSliceOptions[3]

    self.yellowSliceLogic.StartSliceNodeInteraction(2)
    self.yellowSliceNode.SetFieldOfView(yellowFOV[0], yellowFOV[1], yellowFOV[2])
    self.yellowSliceNode.SetSliceOffset(yellowOffset)
    self.yellowSliceLogic.EndSliceNodeInteraction()

    self.comingFromPreopTag = True

  def onRigidCheckBoxClicked(self):

    self.showPreopButton.setStyleSheet(self.STYLE_WHITE_BACKGROUND)
    self.showRigidButton.setStyleSheet(self.STYLE_GRAY_BACKGROUND_WHITE_FONT)
    self.showAffineButton.setStyleSheet(self.STYLE_WHITE_BACKGROUND)
    self.showBSplineButton.setStyleSheet(self.STYLE_WHITE_BACKGROUND)

    # link images
    self.compositeNodeRed.SetLinkedControl(1)
    self.compositNodeYellow.SetLinkedControl(1)

    # set the slice views
    self.compositNodeYellow.SetBackgroundVolumeID(self.registrationResults[self.currentRegistrationResult]['fixedVolume'].GetID())
    self.compositeNodeRed.SetForegroundVolumeID(self.registrationResults[self.currentRegistrationResult]['fixedVolume'].GetID())
    self.compositeNodeRed.SetBackgroundVolumeID(self.registrationResults[self.currentRegistrationResult]['outputVolumeRigid'].GetID())

    if self.comingFromPreopTag:
      self.resetSliceViews()

    #dispNodeTargetsREG = self.outputTargetsRigid.GetDisplayNode()
    #dispNodeTargetsREG.AddViewNodeID(self.yellowSliceNode.GetID())

    # set markups visible
    self.markupsLogic.SetAllMarkupsVisibility(self.outputTargetsRigid,1)
    self.markupsLogic.SetAllMarkupsVisibility(self.outputTargetsAffine,0)
    self.markupsLogic.SetAllMarkupsVisibility(self.outputTargetsBSpline,0)

    # jump slice to show Targets in Yellow
    self.markupsLogic.JumpSlicesToNthPointInMarkup(self.outputTargetsRigid.GetID(),1)

  def onAffineCheckBoxClicked(self):

    self.showPreopButton.setStyleSheet(self.STYLE_WHITE_BACKGROUND)
    self.showRigidButton.setStyleSheet(self.STYLE_WHITE_BACKGROUND)
    self.showAffineButton.setStyleSheet(self.STYLE_GRAY_BACKGROUND_WHITE_FONT)
    self.showBSplineButton.setStyleSheet(self.STYLE_WHITE_BACKGROUND)

    # link images
    self.compositeNodeRed.SetLinkedControl(1)
    self.compositNodeYellow.SetLinkedControl(1)

    # set the slice views
    self.compositNodeYellow.SetBackgroundVolumeID(self.registrationResults[self.currentRegistrationResult]['fixedVolume'].GetID())
    self.compositeNodeRed.SetForegroundVolumeID(self.registrationResults[self.currentRegistrationResult]['fixedVolume'].GetID())
    self.compositeNodeRed.SetBackgroundVolumeID(self.registrationResults[self.currentRegistrationResult]['outputVolumeAffine'].GetID())


    if self.comingFromPreopTag:
      self.resetSliceViews()

    #dispNodeTargetsREG = self.outputTargetsAffine.GetDisplayNode()
    #dispNodeTargetsREG.AddViewNodeID(self.yellowSliceNode.GetID())

    # set markups visible
    self.markupsLogic.SetAllMarkupsVisibility(self.outputTargetsRigid,0)
    self.markupsLogic.SetAllMarkupsVisibility(self.outputTargetsAffine,1)
    self.markupsLogic.SetAllMarkupsVisibility(self.outputTargetsBSpline,0)

    # jump slice to show Targets in Yellow
    self.markupsLogic.JumpSlicesToNthPointInMarkup(self.outputTargetsAffine.GetID(),1)

  def onBSplineCheckBoxClicked(self):

    self.showPreopButton.setStyleSheet(self.STYLE_WHITE_BACKGROUND)
    self.showRigidButton.setStyleSheet(self.STYLE_WHITE_BACKGROUND)
    self.showAffineButton.setStyleSheet(self.STYLE_WHITE_BACKGROUND)
    self.showBSplineButton.setStyleSheet(self.STYLE_GRAY_BACKGROUND_WHITE_FONT)

    # link images
    self.compositeNodeRed.SetLinkedControl(1)
    self.compositNodeYellow.SetLinkedControl(1)

    # set the slice views
    self.compositNodeYellow.SetBackgroundVolumeID(self.registrationResults[self.currentRegistrationResult]['fixedVolume'].GetID())
    self.compositeNodeRed.SetForegroundVolumeID(self.registrationResults[self.currentRegistrationResult]['fixedVolume'].GetID())
    self.compositeNodeRed.SetBackgroundVolumeID(self.registrationResults[self.currentRegistrationResult]['outputVolumeBSpline'].GetID())

    if self.comingFromPreopTag:
      self.resetSliceViews()

    #dispNodeTargetsREG = self.outputTargetsBSpline.GetDisplayNode()
    #dispNodeTargetsREG.AddViewNodeID(self.yellowSliceNode.GetID())

    # set markups visible
    self.markupsLogic.SetAllMarkupsVisibility(self.outputTargetsRigid,0)
    self.markupsLogic.SetAllMarkupsVisibility(self.outputTargetsAffine,0)
    self.markupsLogic.SetAllMarkupsVisibility(self.outputTargetsBSpline,1)

    # jump slice to show Targets in Yellow
    self.markupsLogic.JumpSlicesToNthPointInMarkup(self.outputTargetsBSpline.GetID(),1)

  def resetSliceViews(self):

    # get FOV and offset
    restoredSliceOptions=self.getCurrentSliceViewPositions()
    redOffset=restoredSliceOptions[0]
    yellowOffset=restoredSliceOptions[1]
    redFOV=restoredSliceOptions[2]
    yellowFOV=restoredSliceOptions[3]

    # fit slice view
    self.redSliceLogic.FitSliceToAll()
    self.yellowSliceLogic.FitSliceToAll()

    # reset the slice views
    self.yellowSliceLogic.StartSliceNodeInteraction(2)
    self.yellowSliceNode.SetFieldOfView(yellowFOV[0], yellowFOV[1], yellowFOV[2])
    self.yellowSliceNode.SetSliceOffset(yellowOffset)
    self.yellowSliceLogic.EndSliceNodeInteraction()

    self.redSliceLogic.StartSliceNodeInteraction(2)
    self.redSliceNode.SetFieldOfView(redFOV[0], redFOV[1], redFOV[2])
    self.redSliceNode.SetSliceOffset(redOffset)
    self.redSliceLogic.EndSliceNodeInteraction()

    # reset the tag
    self.comingFromPreopTag=False

  def saveCurrentSliceViewPositions(self):

    # save the current slice view positions
    self.currentSliceOffsetRed = self.redSliceNode.GetSliceOffset()
    self.currentSliceOffsetYellow = self.yellowSliceNode.GetSliceOffset()

    self.currentFOVRed = self.redSliceNode.GetFieldOfView()
    self.currentFOVYellow = self.yellowSliceNode.GetFieldOfView()

  def getCurrentSliceViewPositions(self):
    return [self.currentSliceOffsetRed,self.currentSliceOffsetYellow,self.currentFOVRed,self.currentFOVYellow]

  def onTargetCheckBox(self):

    fiducialNode=slicer.mrmlScene.GetNodesByName('targets-REG').GetItemAsObject(0)
    if self.targetCheckBox.isChecked():
      self.markupsLogic.SetAllMarkupsVisibility(fiducialNode,1)
    if not self.targetCheckBox.isChecked():
      self.markupsLogic.SetAllMarkupsVisibility(fiducialNode,0)

  def onsimulateDataIncomeButton2(self):

    # copy DICOM Files into intraop folder
    imagePath= (self.modulePath +'Resources/Testing/testData_1/')
    intraopPath=self.intraopDataDir
    cmd = ('cp -a '+imagePath+'. '+intraopPath)
    print cmd
    os.system(cmd)

  def onsimulateDataIncomeButton3(self):

    # copy DICOM Files into intraop folder
    imagePath= (self.modulePath +'Resources/Testing/testData_2/')
    intraopPath=self.intraopDataDir
    cmd = ('cp -a '+imagePath+'. '+intraopPath)
    print cmd
    os.system(cmd)

  def onsimulateDataIncomeButton4(self):

    # copy DICOM Files into intraop folder
    imagePath= (self.modulePath +'Resources/Testing/testData_3/')
    intraopPath=self.intraopDataDir
    cmd = ('cp -a '+imagePath+'. '+intraopPath)
    print cmd
    os.system(cmd)

  def onsimulateDataIncomeButton5(self):

    # copy DICOM Files into intraop folder
    imagePath= (self.modulePath +'Resources/Testing/testData_4/')
    intraopPath=self.intraopDataDir
    cmd = ('cp -a '+imagePath+'. '+intraopPath)
    print cmd
    os.system(cmd)

  def configureSliceNodesForPreopData(self):
    # use label contours
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeRed").SetUseLabelOutline(True)
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeYellow").SetUseLabelOutline(True)
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeGreen").SetUseLabelOutline(True)
    # set orientation to axial
    self.redSliceNode.SetOrientationToAxial()

  def loadT2Label(self):
    preopLabelVolumeNode = None
    if slicer.util.loadLabelVolume(self.settings.value('RegistrationModule/preopLocation') + '/t2-label.nrrd'):
      preopLabelVolumeNode = slicer.mrmlScene.GetNodesByName('t2-label').GetItemAsObject(0)
      self.preopLabel = preopLabelVolumeNode
      displayNode = preopLabelVolumeNode.GetDisplayNode()
      displayNode.SetAndObserveColorNodeID('vtkMRMLColorTableNode1')
      # rotate volume to plane
      slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeRed").RotateToVolumePlane(preopLabelVolumeNode)
      slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeYellow").RotateToVolumePlane(preopLabelVolumeNode)
      slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeGreen").RotateToVolumePlane(preopLabelVolumeNode)
    return preopLabelVolumeNode

  def loadPreopVolume(self):
    if slicer.util.loadVolume(self.settings.value('RegistrationModule/preopLocation') + '/t2-N4.nrrd'):
      self.preopVolume = slicer.mrmlScene.GetNodesByName('t2-N4').GetItemAsObject(0)
      self.preopVolume.SetName('volume-PREOP')

  def loadPreopImageVolume(self):
    if slicer.util.loadVolume(self.settings.value('RegistrationModule/preopLocation') + '/t2-N4.nrrd'):
      preopImageVolumeNode = slicer.mrmlScene.GetNodesByName('t2-N4_1').GetItemAsObject(0)
      self.preopVolumeSelector.setCurrentNode(preopImageVolumeNode)

  def loadPreopTargets(self):
    # Load preop Targets that remain reserved to be shown after registration as preop Targets
    if slicer.util.loadMarkupsFiducialList(self.settings.value('RegistrationModule/preopLocation') + '/Targets.fcsv'):
      self.targetsPreop = slicer.mrmlScene.GetNodesByName('Targets').GetItemAsObject(0)
      self.targetsPreop.SetName('targets-PREOP')

  def loadPreopData(self):

    self.configureSliceNodesForPreopData()
    self.loadT2Label()
    self.loadPreopVolume()
    self.loadPreopImageVolume()
    self.loadPreopTargets()

    logging.debug('TARGETS PREOP')
    logging.debug(slicer.modules.RegistrationModuleWidget.targetsPreop)

    """
    # load targets for rigid transformation
    slicer.util.loadMarkupsFiducialList(self.settings.value('RegistrationModule/preopLocation')+'/Targets.fcsv')
    self.targetsRigid=slicer.mrmlScene.GetNodesByName('Targets').GetItemAsObject(0)
    self.targetsRigid.SetName('targets-RIGID')

    # load targets for affine transformation
    slicer.util.loadMarkupsFiducialList(self.settings.value('RegistrationModule/preopLocation')+'/Targets.fcsv')
    self.targetsAffine=slicer.mrmlScene.GetNodesByName('Targets').GetItemAsObject(0)
    self.targetsAffine.SetName('targets-AFFINE')

    # load targets for bspline transformation
    slicer.util.loadMarkupsFiducialList(self.settings.value('RegistrationModule/preopLocation')+'/Targets.fcsv')
    self.targetsBSpline=slicer.mrmlScene.GetNodesByName('Targets').GetItemAsObject(0)
    self.targetsBSpline.SetName('targets-BSPLINE')
    """

    # set markups visible
    """
    self.markupsLogic.SetAllMarkupsVisibility(self.targetsRigid,0)
    self.markupsLogic.SetAllMarkupsVisibility(self.targetsAffine,0)
    self.markupsLogic.SetAllMarkupsVisibility(self.targetsBSpline,0)
    """
    self.markupsLogic.SetAllMarkupsVisibility(self.targetsPreop,1)

    # set markups for registration
    self.fiducialSelector.setCurrentNode(self.targetsPreop)

    # jump to first markup slice
    self.markupsLogic.JumpSlicesToNthPointInMarkup(self.targetsPreop.GetID(),1)

    # Set Fiducial Properties
    markupsDisplayNode=self.targetsPreop.GetDisplayNode()
    markupsDisplayNode.SetTextScale(1.9)
    markupsDisplayNode.SetGlyphScale(1.0)

    self.compositeNodeRed.SetLabelOpacity(1)

    # set Layout to redSliceViewOnly
    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)

    # zoom in (in red slice view)
    fovRed=self.redSliceNode.GetFieldOfView()

    self.redSliceLogic.StartSliceNodeInteraction(2)
    self.redSliceNode.SetFieldOfView(fovRed[0] * 0.5, fovRed[1] * 0.5, fovRed[2])
    self.redSliceLogic.EndSliceNodeInteraction()

  def patientCheckAfterImport(self,directory,fileList):
    for currentFile in fileList:
      if currentFile != ".DS_Store" and self.dicomDatabase.fileValue(directory+'/'+currentFile,self.PATIENT_ID) != self.currentID:
        incomePatient = self.dicomDatabase.fileValue(str(directory+'/'+fileList[2]),self.PATIENT_ID)
        return self.confirmDialog(message='WARNING: You selected Patient ID ' + self.currentID +
                                 ', but Patient ID '+incomePatient+' just arrived in the income folder.',
                                  title="Patients Not Matching")

  @staticmethod
  def confirmDialog(message, title='PCampReview'):
    result = qt.QMessageBox.question(slicer.util.mainWindow(), title, message,
                                     qt.QMessageBox.Ok | qt.QMessageBox.Cancel)
    return result == qt.QMessageBox.Ok

  def getSelectedSeriesFromSelector(self):
    if self.seriesItems:
      checkedItems = [x for x in self.seriesItems if x.checkState()]
      self.selectedSeries=[]

      for x in checkedItems:
        self.selectedSeries.append(x.text())

    return self.selectedSeries

  def onStartSegmentationButton(self):

    # set current referenceVolume as background volume
    self.compositeNodeRed.SetBackgroundVolumeID(self.referenceVolumeSelector.currentNode().GetID())
    self.redSliceLogic.FitSliceToAll()

    # clear current Label
    self.compositeNodeRed.SetLabelVolumeID(None)

    # hide existing labels
    # self.compositNodeRed.SetLabelOpacity(0)

    self.quickSegmentationFlag=1

    self.setQuickSegmentationModeON()

    self.logic.runQuickSegmentationMode()
    self.logic.inputMarkup.AddObserver(vtk.vtkCommand.ModifiedEvent,self.updateUndoRedoButtons)

  def setQuickSegmentationModeON(self):
    self.startLabelSegmentationButton.setEnabled(0)
    self.startQuickSegmentationButton.setEnabled(0)
    self.applySegmentationButton.setEnabled(1)
    self.deactivateUndoRedoButtons()
    self.deletedMarkups.Reset()

  def setQuickSegmentationModeOFF(self):
    self.startLabelSegmentationButton.setEnabled(1)
    self.startQuickSegmentationButton.setEnabled(1)
    self.applySegmentationButton.setEnabled(0)
    self.deactivateUndoRedoButtons()

    # reset persistent fiducial tol
    interactionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLInteractionNodeSingleton")
    interactionNode.SwitchToViewTransformMode()
    interactionNode.SetPlaceModePersistence(0)

  def changeOpacity(self,value):
    self.compositeNodeRed.SetForegroundOpacity(value)

  def onApplySegmentationButton(self):

    if self.quickSegmentationFlag==1:

      # create a labelmap from the model

      # set parameter for modelToLabelmap CLI Module
      inputVolume=self.referenceVolumeSelector.currentNode()

      # get InputModel
      clippingModel=slicer.mrmlScene.GetNodesByName('clipModelNode').GetItemAsObject(0)

      # run CLI-Module

      # check, if there are enough targets set to create the model and call the CLI
      if slicer.mrmlScene.GetNodesByName('inputMarkupNode').GetItemAsObject(0).GetNumberOfFiducials() > 2:

        labelname=(slicer.modules.RegistrationModuleWidget.referenceVolumeSelector.currentNode().GetName()+ '-label')
        self.currentIntraopLabel = self.logic.modelToLabelmap(inputVolume,clippingModel)
        self.currentIntraopLabel.SetName(labelname)

        # set color table
        displayNode=self.currentIntraopLabel.GetDisplayNode()
        displayNode.SetAndObserveColorNodeID('vtkMRMLColorTableNode1')

        # set Labelmap for Registration
        self.intraopLabelSelector.setCurrentNode(self.currentIntraopLabel)

      # re-set Buttons
      else:
        slicer.mrmlScene.RemoveNode(slicer.mrmlScene.GetNodesByName('clipModelNode').GetItemAsObject(0))
        print ('deleted ModelNode')
        slicer.mrmlScene.RemoveNode(slicer.mrmlScene.GetNodesByName('inputMarkupNode').GetItemAsObject(0))
        print ('deleted inputMarkupNode')

      self.setQuickSegmentationModeOFF()
      self.quickSegmentationFlag=0

      # set up screen
      self.setupScreenAfterSegmentation()

    elif self.labelSegmentationFlag==1:

      # dilate label
      editUtil = EditorLib.EditUtil.EditUtil()
      logic = EditorLib.DilateEffectLogic(editUtil.getSliceLogic())
      logic.erode(0,'4',1)

      # reset cursor to default
      self.editorParameterNode.SetParameter('effect','DefaultTool')

      # set Labelmap for Registration
      labelname=(slicer.modules.RegistrationModuleWidget.referenceVolumeSelector.currentNode().GetName()+ '-label')
      self.currentIntraopLabel=slicer.mrmlScene.GetNodesByName(labelname).GetItemAsObject(0)
      self.intraopLabelSelector.setCurrentNode(self.currentIntraopLabel)

      self.labelSegmentationFlag=0

      # set up screen
      self.setupScreenAfterSegmentation()

    else:
      #TODO: tell user that he needs to do segmentation before hin apply
      pass

    # reset options
    self.startQuickSegmentationButton.setEnabled(1)
    self.startLabelSegmentationButton.setEnabled(1)
    self.applySegmentationButton.setEnabled(0)

  def setupScreenAfterSegmentation(self):

    # set up layout
    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutSideBySideView)

    # set up preop image and label
    self.compositeNodeRed.SetReferenceBackgroundVolumeID(self.preopVolume.GetID())
    self.compositeNodeRed.SetLabelVolumeID(self.preopLabel.GetID())

    # set up intraop image and label
    self.compositNodeYellow.SetReferenceBackgroundVolumeID(self.referenceVolumeSelector.currentNode().GetID())
    self.compositNodeYellow.SetLabelVolumeID(self.currentIntraopLabel.GetID())

    # rotate volume to plane
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeRed").RotateToVolumePlane(self.preopVolume)
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeYellow").RotateToVolumePlane(self.currentIntraopLabel)

    # first - fit slice view
    self.redSliceLogic.FitSliceToAll()
    self.yellowSliceLogic.FitSliceToAll()

    # zoom in propertly
    self.yellowSliceNode.SetFieldOfView(86, 136, 3.5)
    self.redSliceNode.SetFieldOfView(86, 136, 3.5)

    # set Tab enabled
    self.tabBar.setTabEnabled(2,True)

    # get the slice Offset to reset yellow after JumpSlicesTo
    offset=self.yellowSliceNode.GetSliceOffset()

    # jump slice to show Targets
    self.markupsLogic.JumpSlicesToNthPointInMarkup(self.targetsPreop.GetID(),1)

    self.yellowSliceNode.SetSliceOffset(offset)

    # change to Registration Tab
    self.tabBar.currentIndex=2

  def onStartLabelSegmentationButton(self):

    # clear current Label
    self.compositeNodeRed.SetLabelVolumeID(None)

    # disable QuickSegmentationButton
    self.startQuickSegmentationButton.setEnabled(0)
    self.startLabelSegmentationButton.setEnabled(0)
    self.applySegmentationButton.setEnabled(1)
    self.labelSegmentationFlag=1

    self.compositeNodeRed.SetBackgroundVolumeID(self.referenceVolumeSelector.currentNode().GetID())

    # create new labelmap and set
    referenceVolume=self.referenceVolumeSelector.currentNode()
    volumesLogic = slicer.modules.volumes.logic()
    intraopLabel = volumesLogic.CreateAndAddLabelVolume(slicer.mrmlScene,referenceVolume,
                                                        referenceVolume.GetName() + '-label' )
    selectionNode = slicer.app.applicationLogic().GetSelectionNode()
    selectionNode.SetReferenceActiveVolumeID( referenceVolume.GetID() )
    selectionNode.SetReferenceActiveLabelVolumeID( intraopLabel.GetID() )
    slicer.app.applicationLogic().PropagateVolumeSelection(50)

    # show label
    self.compositeNodeRed.SetLabelOpacity(1)

    # set color table
    print ('intraopLabelID : '+str(intraopLabel.GetID()))

    # set color table
    displayNode=intraopLabel.GetDisplayNode()
    displayNode.SetAndObserveColorNodeID('vtkMRMLColorTableNode1')

    editUtil=slicer.modules.RegistrationModuleWidget.editUtil
    parameterNode=editUtil.getParameterNode()
    parameterNode.SetParameter('effect','DrawEffect')

    # set label properties
    editUtil.setLabel(1)
    editUtil.setLabelOutline(1)

  def createRegistrationResult(self,name,params,output):

    # this function stores information and nodes of a single
    # registration run to be able to switch between results.

      # this is a summary for bspline registration output

    summary = {'index': str(len(self.registrationResults) + 1),
               'name' : name,
               'movingVolume' : params[0],
               'fixedVolume' : params[1],
               'movingLabel' : params[2],
               'fixedLabel' : params[3],
               'targets' : params[4],
               'outputVolumeRigid' : output[0],
               'outputVolumeAffine' : output[1],
               'outputVolumeBSpline' :output[2],
               'outputTransformRigid' :output[3],
               'outputTransformAffine' :output[4],
               'outputTransformBSpline' :output[5],
               'outputTargetsRigid' :output[6][0],
               'outputTargetsAffine' :output[6][1],
               'outputTargetsBSpline' :output[6][2]}

    # add to results
    self.registrationResults.append(summary)

    print ('# ___________________________  registration output  ________________________________')
    print summary
    print ('# __________________________________________________________________________________')

    return True

  def onApplyRegistrationClicked(self):

    fixedVolume= self.intraopVolumeSelector.currentNode()
    fixedLabel=self.intraopLabelSelector.currentNode()
    movingLabel=self.preopLabelSelector.currentNode()
    targets=self.fiducialSelector.currentNode()

    sourceVolumeNode = self.preopVolumeSelector.currentNode()
    volumesLogic = slicer.modules.volumes.logic()
    movingVolume = volumesLogic.CloneVolume(slicer.mrmlScene, sourceVolumeNode, 'movingVolume-PREOP-INTRAOP')

    params=[]
    params.append(sourceVolumeNode)
    params.append(fixedVolume)
    params.append(movingLabel)
    params.append(fixedLabel)
    params.append(targets)

    registrationOutput=[]
    registrationOutput=self.logic.applyBSplineRegistration(fixedVolume,movingVolume,fixedLabel,movingLabel,targets)

    self.outputVolumeRigid=registrationOutput[0]
    self.outputVolumeAffine=registrationOutput[1]
    self.outputVolumeBSpline=registrationOutput[2]
    self.outputTransformRigid=registrationOutput[3]
    self.outputTransformAffine=registrationOutput[4]
    self.outputTransformBSpline=registrationOutput[5]
    self.outputTargetsRigid=registrationOutput[6][0]
    self.outputTargetsAffine=registrationOutput[6][1]
    self.outputTargetsBSpline=registrationOutput[6][2]


    slicer.mrmlScene.AddNode(self.outputTargetsRigid)
    slicer.mrmlScene.AddNode(self.outputTargetsAffine)
    slicer.mrmlScene.AddNode(self.outputTargetsBSpline)

    # create a summary
    name=str(self.currentIntraopVolume.GetName())
    summary = self.createRegistrationResult(name,params,registrationOutput)

    # update the combo box
    self.updateRegistrationResultSelector()

    # set up screens
    self.setupScreenAfterRegistration()

    # select BSpline view
    self.onBSplineCheckBoxClicked()

    print ('Registration Function is done')

  def setupScreenAfterRegistration(self):

    index=int(len(self.registrationResults)-1)

    print 'index = '+str(index)
    self.compositeNodeRed.SetForegroundVolumeID(self.currentIntraopVolume.GetID())
    self.compositeNodeRed.SetBackgroundVolumeID(self.registrationResults[index]['outputVolumeBSpline'].GetID())
    self.compositNodeYellow.SetBackgroundVolumeID(self.currentIntraopVolume.GetID())

    self.redSliceLogic.FitSliceToAll()
    self.yellowSliceLogic.FitSliceToAll()


    # remove view node ID's from Red Slice view
    dispNodeRigid=self.outputTargetsRigid.GetDisplayNode()
    dispNodeAffine=self.outputTargetsAffine.GetDisplayNode()
    dispNodeBSpline=self.outputTargetsBSpline.GetDisplayNode()
    dispNodePreop=self.targetsPreop.GetDisplayNode()

    dispNodeRigid.RemoveAllViewNodeIDs()
    dispNodeAffine.RemoveAllViewNodeIDs()
    dispNodeBSpline.RemoveAllViewNodeIDs()
    dispNodePreop.RemoveAllViewNodeIDs()

    dispNodePreop.AddViewNodeID(self.redSliceNode.GetID())
    dispNodeRigid.AddViewNodeID(self.yellowSliceNode.GetID())
    dispNodeAffine.AddViewNodeID(self.yellowSliceNode.GetID())
    dispNodeBSpline.AddViewNodeID(self.yellowSliceNode.GetID())


    # set fiducial place mode back to regular view mode
    interactionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLInteractionNodeSingleton")
    interactionNode.SwitchToViewTransformMode()
    interactionNode.SetPlaceModePersistence(0)

    # set Side By Side View to compare volumes
    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutSideBySideView)

    # Hide Labels
    self.compositeNodeRed.SetLabelOpacity(0)
    self.compositNodeYellow.SetLabelOpacity(0)

    # set both orientations to axial
    self.redSliceNode.SetOrientationToAxial()
    self.yellowSliceNode.SetOrientationToAxial()

    # zoom in
    fovRed=self.redSliceNode.GetFieldOfView()
    fovYellow=self.yellowSliceNode.GetFieldOfView()

    self.redSliceLogic.StartSliceNodeInteraction(2)
    self.redSliceNode.SetFieldOfView(fovRed[0] * 0.5, fovRed[1] * 0.5, fovRed[2])
    self.redSliceLogic.EndSliceNodeInteraction()

    self.yellowSliceLogic.StartSliceNodeInteraction(2)
    self.yellowSliceNode.SetFieldOfView(fovYellow[0] * 0.5, fovYellow[1] * 0.5, fovYellow[2])
    self.yellowSliceLogic.EndSliceNodeInteraction()

    # enable Evaluation Section
    self.tabBar.setTabEnabled(3,True)

    # switch to Evaluation Section
    self.tabWidget.setCurrentIndex(3)

  def checkTabAfterImport(self):

    # change icon of tabBar if user is not in Data selection tab
    if not self.tabWidget.currentIndex == 0:
      self.tabBar.setTabIcon(0,self.newImageDataIcon)


class RegistrationModuleLogic(ScriptedLoadableModuleLogic):

  def __init__(self, parent=None):
    ScriptedLoadableModuleLogic.__init__(self, parent)
    self.inputMarkup = None

  def applyBSplineRegistration(self,fixedVolume,movingVolume,fixedLabel,movingLabel,targets):

    if fixedVolume and movingVolume and fixedLabel and movingLabel:

     ##### OUTPUT TRANSFORMS

     # define output linear Rigid transform
     outputTransformRigid=slicer.vtkMRMLLinearTransformNode()
     outputTransformRigid.SetName('transform-Rigid')

     # define output linear Affine transform
     outputTransformAffine=slicer.vtkMRMLLinearTransformNode()
     outputTransformAffine.SetName('transform-Affine')

     # define output BSpline transform
     outputTransformBSpline=slicer.vtkMRMLBSplineTransformNode()
     outputTransformBSpline.SetName('transform-BSpline')

     ##### OUTPUT VOLUMES

     # TODO: create storage nodes

     # define output volume Rigid
     outputVolumeRigid=slicer.vtkMRMLScalarVolumeNode()
     outputVolumeRigid.SetName('reg-Rigid')

     # define output volume Affine
     outputVolumeAffine=slicer.vtkMRMLScalarVolumeNode()
     outputVolumeAffine.SetName('reg-Affine')

     # define output volume BSpline
     outputVolumeBSpline=slicer.vtkMRMLScalarVolumeNode()
     outputVolumeBSpline.SetName('reg-BSpline')

     # add output nodes
     slicer.mrmlScene.AddNode(outputVolumeRigid)
     slicer.mrmlScene.AddNode(outputVolumeBSpline)
     slicer.mrmlScene.AddNode(outputVolumeAffine)
     slicer.mrmlScene.AddNode(outputTransformRigid)
     slicer.mrmlScene.AddNode(outputTransformAffine)
     slicer.mrmlScene.AddNode(outputTransformBSpline)

     #   ++++++++++      RIGID REGISTRATION       ++++++++++

     paramsRigid = {'fixedVolume': fixedVolume,
                    'movingVolume': movingVolume,
                    'fixedBinaryVolume' : fixedLabel,
                    'movingBinaryVolume' : movingLabel,
                    'outputTransform' : outputTransformRigid.GetID(),
                    'outputVolume' : outputVolumeRigid.GetID(),
                    'maskProcessingMode' : "ROI",
                    'initializeTransformMode' : "useCenterOfROIAlign",
                    'useRigid' : True,
                    'useAffine' : False,
                    'useScaleVersor3D' : False,
                    'useScaleSkewVersor3D' : False,
                    'useROIBSpline' : False,
                    'useBSpline' : False,}

     # run Rigid Registration
     self.cliNode=None
     self.cliNode=slicer.cli.run(slicer.modules.brainsfit, self.cliNode, paramsRigid, wait_for_completion = True)

     #   ++++++++++      AFFINE REGISTRATION       ++++++++++

     paramsAffine = {'fixedVolume': fixedVolume,
               'movingVolume': movingVolume,
               'fixedBinaryVolume' : fixedLabel,
               'movingBinaryVolume' : movingLabel,
               'outputTransform' : outputTransformAffine.GetID(),
               'outputVolume' : outputVolumeAffine.GetID(),
               'maskProcessingMode' : "ROI",
               #'initializeTransformMode' : "useCenterOfROIAlign",
               'useAffine' : True,
               'initialTransform' : outputTransformRigid}

     # run Affine Registration
     self.cliNode=None
     self.cliNode=slicer.cli.run(slicer.modules.brainsfit, self.cliNode, paramsAffine, wait_for_completion = True)

     #   ++++++++++      BSPLINE REGISTRATION       ++++++++++

     paramsBSpline = {'fixedVolume': fixedVolume,
                      'movingVolume': movingVolume,
                      'outputVolume' : outputVolumeBSpline.GetID(),
                      'bsplineTransform' : outputTransformBSpline.GetID(),
                      'movingBinaryVolume' : movingLabel,
                      'fixedBinaryVolume' : fixedLabel,
                      #'initializeTransformMode' : "useCenterOfROIAlign",
                      'samplingPercentage' : "0.002",
                      'useRigid' : True,
                      'useAffine' : True,
                      'useROIBSpline' : True,
                      'useBSpline' : True,
                      'useScaleVersor3D' : True,
                      'useScaleSkewVersor3D' : True,
                      'splineGridSize' : "3,3,3",
                      'numberOfIterations' : "1500",
                      'maskProcessing' : "ROI",
                      'outputVolumePixelType' : "float",
                      'backgroundFillValue' : "0",
                      'maskInferiorCutOffFromCenter' : "1000",
                      'interpolationMode' : "Linear",
                      'minimumStepLength' : "0.005",
                      'translationScale' : "1000",
                      'reproportionScale' : "1",
                      'skewScale' : "1",
                      'numberOfHistogramBins' : "50",
                      'numberOfMatchPoints': "10",
                      'fixedVolumeTimeIndex' : "0",
                      'movingVolumeTimeIndex' : "0",
                      'medianFilterSize' : "0,0,0",
                      'ROIAutoDilateSize' : "0",
                      'relaxationFactor' : "0.5",
                      'maximumStepLength' : "0.2",
                      'failureExitCode' : "-1",
                      'numberOfThreads': "-1",
                      'debugLevel': "0",
                      'costFunctionConvergenceFactor' : "1.00E+09",
                      'projectedGradientTolerance' : "1.00E-05",
                      'maxBSplineDisplacement' : "0",
                      'maximumNumberOfEvaluations' : "900",
                      'maximumNumberOfCorrections': "25",
                      'metricSamplingStrategy' : "Random",
                      'costMetric' : "MMI",
                      'removeIntensityOutliers' : "0",
                      'ROIAutoClosingSize' : "9",
                      'maskProcessingMode' : "ROI",
                      'initialTransform' : outputTransformAffine
                      }


     # run BSpline Registration
     self.cliNode=None
     self.cliNode=slicer.cli.run(slicer.modules.brainsfit, self.cliNode, paramsBSpline, wait_for_completion = True)


     #   ++++++++++      TRANSFORM FIDUCIALS        ++++++++++


     if targets:

       # clone targets
       originalTargets=slicer.mrmlScene.GetNodesByName('targets-PREOP').GetItemAsObject(0)

       mlogic=slicer.modules.markups.logic()
       mlogic.AddNewFiducialNode('targets-RIGID',slicer.mrmlScene)
       mlogic.AddNewFiducialNode('targets-AFFINE',slicer.mrmlScene)
       mlogic.AddNewFiducialNode('targets-BSPLINE',slicer.mrmlScene)

       rigidTargets=slicer.mrmlScene.GetNodesByName('targets-RIGID').GetItemAsObject(0)
       affineTargets=slicer.mrmlScene.GetNodesByName('targets-AFFINE').GetItemAsObject(0)
       bSplineTargets=slicer.mrmlScene.GetNodesByName('targets-BSPLINE').GetItemAsObject(0)

       self.cloneFiducials(originalTargets,rigidTargets)
       self.cloneFiducials(originalTargets,affineTargets)
       self.cloneFiducials(originalTargets,bSplineTargets)

       print ("Perform Target Transform")

       # get transforms
       transformNodeRigid=slicer.mrmlScene.GetNodesByName('transform-Rigid').GetItemAsObject(0)
       transformNodeAffine=slicer.mrmlScene.GetNodesByName('transform-Affine').GetItemAsObject(0)
       transformNodeBSpline=slicer.mrmlScene.GetNodesByName('transform-BSpline').GetItemAsObject(0)

       # get fiducials
       #rigidTargets=slicer.mrmlScene.GetNodesByName('targets-RIGID').GetItemAsObject(0)
       #affineTargets=slicer.mrmlScene.GetNodesByName('targets-AFFINE').GetItemAsObject(0)
       #bSplineTargets=slicer.mrmlScene.GetNodesByName('targets-BSPLINE').GetItemAsObject(0)

       # apply transforms
       rigidTargets.SetAndObserveTransformNodeID(transformNodeRigid.GetID())
       affineTargets.SetAndObserveTransformNodeID(transformNodeAffine.GetID())
       bSplineTargets.SetAndObserveTransformNodeID(transformNodeBSpline.GetID())

       # harden the transforms
       tfmLogic = slicer.modules.transforms.logic()
       tfmLogic.hardenTransform(rigidTargets)
       tfmLogic.hardenTransform(affineTargets)
       tfmLogic.hardenTransform(bSplineTargets)

       self.renameFiducials(rigidTargets)
       self.renameFiducials(affineTargets)
       self.renameFiducials(bSplineTargets)

       outputTargets=[]
       outputTargets.append(rigidTargets)
       outputTargets.append(affineTargets)
       outputTargets.append(bSplineTargets)

     return [outputVolumeRigid, outputVolumeAffine, outputVolumeBSpline,
             outputTransformRigid, outputTransformAffine, outputTransformBSpline, outputTargets]

  def cloneFiducials(self,originalFidList,newFidList):
    for i in range(originalFidList.GetNumberOfFiducials()):
      pos=[0.0,0.0,0.0]
      originalFidList.GetNthFiducialPosition(i,pos)
      name=originalFidList.GetNthFiducialLabel(i)
      #print 'name'+name
      #print 'parsing position : '+str(pos)
      newFidList.AddFiducial(pos[0],pos[1],pos[2])
      newFidList.SetNthFiducialLabel(i,name)

  def applyReRegistration(self,fixedVolume,movingVolume,fixedLabel,targets,lastRigidTfm):

    """
    # rigid
    BFRegister(fixed=fixedImage,moving=movingImage,fixedMask=fixedMask,rigidTfm=rigidTfm,log=log,initialTfm=latestRigidTfm)
    # affine
    BFRegister(fixed=fixedImage,moving=movingImage,fixedMask=fixedMask,affineTfm=affineTfm,initTfm=rigidTfm,log=log)
    # bspline
    BFRegister(fixed=fixedImage,moving=movingImage,fixedMask=fixedMask,bsplineTfm=bsplineTfm,log=log,initialTfm=affineTfm)
    """

    if fixedVolume and movingVolume and fixedLabel and lastRigidTfm:
     ##### OUTPUT TRANSFORMS

     # define output linear Rigid transform
     outputTransformRigid=slicer.vtkMRMLLinearTransformNode()
     outputTransformRigid.SetName('transform-REREG-Rigid')

     # define output linear Affine transform
     outputTransformAffine=slicer.vtkMRMLLinearTransformNode()
     outputTransformAffine.SetName('transform-REREG-Affine')

     # define output BSpline transform
     outputTransformBSpline=slicer.vtkMRMLBSplineTransformNode()
     outputTransformBSpline.SetName('transform-REREG-BSpline')

     ##### OUTPUT VOLUMES

     # TODO: create storage nodes

     # define output volume Rigid
     outputVolumeRigid=slicer.vtkMRMLScalarVolumeNode()
     outputVolumeRigid.SetName('Rereg-Rigid')

     # define output volume Affine
     outputVolumeAffine=slicer.vtkMRMLScalarVolumeNode()
     outputVolumeAffine.SetName('Rereg-Affine')

     # define output volume BSpline
     outputVolumeBSpline=slicer.vtkMRMLScalarVolumeNode()
     outputVolumeBSpline.SetName('Rereg-BSpline')

     # add output nodes
     slicer.mrmlScene.AddNode(outputVolumeRigid)
     slicer.mrmlScene.AddNode(outputVolumeBSpline)
     slicer.mrmlScene.AddNode(outputVolumeAffine)
     slicer.mrmlScene.AddNode(outputTransformRigid)
     slicer.mrmlScene.AddNode(outputTransformAffine)
     slicer.mrmlScene.AddNode(outputTransformBSpline)

     #   ++++++++++      RIGID REGISTRATION       ++++++++++

     paramsRigid = {'fixedVolume': fixedVolume,
                    'movingVolume': movingVolume,
                    'fixedBinaryVolume' : fixedLabel,
                    # 'movingBinaryVolume' : movingLabel,
                    'outputTransform' : outputTransformRigid.GetID(),
                    'outputVolume' : outputVolumeRigid.GetID(),
                    'maskProcessingMode' : "ROI",
                    # 'initializeTransformMode' : "useCenterOfROIAlign",
                    'useRigid' : True,
                    'useAffine' : False,
                    'useScaleVersor3D' : False,
                    'useScaleSkewVersor3D' : False,
                    'useROIBSpline' : False,
                    'useBSpline' : False,
                    'initialTransform':lastRigidTfm}

     # run Rigid Registration
     self.cliNode=None
     self.cliNode=slicer.cli.run(slicer.modules.brainsfit, self.cliNode, paramsRigid, wait_for_completion = True)

     #   ++++++++++      AFFINE REGISTRATION       ++++++++++

     paramsAffine = {'fixedVolume': fixedVolume,
                     'movingVolume': movingVolume,
                     'fixedBinaryVolume' : fixedLabel,
                     # 'movingBinaryVolume' : movingLabel,
                     'outputTransform' : outputTransformAffine.GetID(),
                     'outputVolume' : outputVolumeAffine.GetID(),
                     'maskProcessingMode' : "ROI",
                     # 'initializeTransformMode' : True,
                     'useAffine' : True,
                     'initialTransform' : outputTransformRigid}

     # run Affine Registration
     self.cliNode=None
     self.cliNode=slicer.cli.run(slicer.modules.brainsfit, self.cliNode, paramsAffine, wait_for_completion = True)

     #   ++++++++++      BSPLINE REGISTRATION       ++++++++++

     paramsBSpline = {'fixedVolume': fixedVolume,
                      'movingVolume': movingVolume,
                      'outputVolume' : outputVolumeBSpline.GetID(),
                      'bsplineTransform' : outputTransformBSpline.GetID(),
                      # 'movingBinaryVolume' : movingLabel,
                      'fixedBinaryVolume' : fixedLabel,
                      # 'initializeTransformMode' : "useCenterOfROIAlign",
                      # 'samplingPercentage' : "0.002",
                      'useRigid' : True,
                      'useAffine' : True,
                      'useROIBSpline' : True,
                      'useBSpline' : True,
                      'useScaleVersor3D' : True,
                      'useScaleSkewVersor3D' : True,
                      'splineGridSize' : "3,3,3",
                      'numberOfIterations' : "1500",
                      'maskProcessing' : "ROI",
                      'outputVolumePixelType' : "float",
                      'backgroundFillValue' : "0",
                      # 'maskInferiorCutOffFromCenter' : "1000",
                      'interpolationMode' : "Linear",
                      'minimumStepLength' : "0.005",
                      'translationScale' : "1000",
                      'reproportionScale' : "1",
                      'skewScale' : "1",
                      # 'numberOfHistogramBins' : "50",
                      # 'numberOfMatchPoints': "10",
                      'fixedVolumeTimeIndex' : "0",
                      'movingVolumeTimeIndex' : "0",
                      'medianFilterSize' : "0,0,0",
                      'ROIAutoDilateSize' : "0",
                      'relaxationFactor' : "0.5",
                      'maximumStepLength' : "0.2",
                      'failureExitCode' : "-1",
                      'numberOfThreads': "-1",
                      'debugLevel': "0",
                      'costFunctionConvergenceFactor' : "1.00E+09",
                      'projectedGradientTolerance' : "1.00E-05",
                      'maxBSplineDisplacement' : "0",
                      'maximumNumberOfEvaluations' : "900",
                      'maximumNumberOfCorrections': "25",
                      # 'metricSamplingStrategy' : "Random",
                      # 'costMetric' : "MMI",
                      'removeIntensityOutliers' : "0",
                      'ROIAutoClosingSize' : "9",
                      'maskProcessingMode' : "ROI",
                      #'initialTransform' : outputTransformAffine
                      }


     # run BSpline Registration
     self.cliNode=None
     self.cliNode=slicer.cli.run(slicer.modules.brainsfit, self.cliNode, paramsBSpline, wait_for_completion = True)


     #   ++++++++++      TRANSFORM FIDUCIALS        ++++++++++


     if targets:

       # clone targets
       originalTargets=targets

       mlogic=slicer.modules.markups.logic()
       mlogic.AddNewFiducialNode('targets-REREG-RIGID',slicer.mrmlScene)
       mlogic.AddNewFiducialNode('targets-REREG-AFFINE',slicer.mrmlScene)
       mlogic.AddNewFiducialNode('targets-REREG-BSPLINE',slicer.mrmlScene)

       rigidTargets=slicer.mrmlScene.GetNodesByName('targets-REREG-RIGID').GetItemAsObject(0)
       affineTargets=slicer.mrmlScene.GetNodesByName('targets-REREG-AFFINE').GetItemAsObject(0)
       bSplineTargets=slicer.mrmlScene.GetNodesByName('targets-REREG-BSPLINE').GetItemAsObject(0)

       self.cloneFiducials(originalTargets,rigidTargets)
       self.cloneFiducials(originalTargets,affineTargets)
       self.cloneFiducials(originalTargets,bSplineTargets)

       print ("Perform Target Transform")

       # get transforms
       transformNodeRigid=slicer.mrmlScene.GetNodesByName('transform-REREG-Rigid').GetItemAsObject(0)
       transformNodeAffine=slicer.mrmlScene.GetNodesByName('transform-REREG-Affine').GetItemAsObject(0)
       transformNodeBSpline=slicer.mrmlScene.GetNodesByName('transform-REREG-BSpline').GetItemAsObject(0)

       # get fiducials
       #rigidTargets=slicer.mrmlScene.GetNodesByName('targets-RIGID').GetItemAsObject(0)
       #affineTargets=slicer.mrmlScene.GetNodesByName('targets-AFFINE').GetItemAsObject(0)
       #bSplineTargets=slicer.mrmlScene.GetNodesByName('targets-BSPLINE').GetItemAsObject(0)

       # apply transforms
       rigidTargets.SetAndObserveTransformNodeID(transformNodeRigid.GetID())
       affineTargets.SetAndObserveTransformNodeID(transformNodeAffine.GetID())
       bSplineTargets.SetAndObserveTransformNodeID(transformNodeBSpline.GetID())

       # harden the transforms
       tfmLogic = slicer.modules.transforms.logic()
       tfmLogic.hardenTransform(rigidTargets)
       tfmLogic.hardenTransform(affineTargets)
       tfmLogic.hardenTransform(bSplineTargets)

       self.renameFiducials(rigidTargets)
       self.renameFiducials(affineTargets)
       self.renameFiducials(bSplineTargets)

       outputTargets=[]
       outputTargets.append(rigidTargets)
       outputTargets.append(affineTargets)
       outputTargets.append(bSplineTargets)

     return [outputVolumeRigid, outputVolumeAffine, outputVolumeBSpline,
             outputTransformRigid, outputTransformAffine, outputTransformBSpline, outputTargets]

  def renameFiducials(self,fiducialNode):
    # rename the targets to "[targetname]-REG"
    numberOfTargets=fiducialNode.GetNumberOfFiducials()
    print ('number of targets : '+str(numberOfTargets))

    for index in range(numberOfTargets):
      oldname=fiducialNode.GetNthFiducialLabel(index)
      fiducialNode.SetNthFiducialLabel(index,str(oldname)+'-REG')
      print ('changed name from '+oldname+' to '+str(oldname)+'-REG')

  def initializeListener(self,directory):

    numberOfFiles = len([item for item in os.listdir(directory)])
    self.temp=numberOfFiles
    self.directory=directory
    self.setlastNumberOfFiles(numberOfFiles)
    self.createCurrentFileList(directory)
    self.startTimer()

  def startTimer(self):
    numberOfFiles = len([item for item in os.listdir(self.directory)])

    if self.getlastNumberOfFiles() < numberOfFiles:
     self.waitingForSeriesToBeCompleted()

     self.setlastNumberOfFiles(numberOfFiles)
     qt.QTimer.singleShot(500,self.startTimer)

    else:
     self.setlastNumberOfFiles(numberOfFiles)
     qt.QTimer.singleShot(500,self.startTimer)

  def createCurrentFileList(self,directory):

    self.currentFileList=[]
    for item in os.listdir(directory):
      self.currentFileList.append(item)

    if len(self.currentFileList) > 1:
      self.thereAreFilesInTheFolderFlag = 1
      self.importDICOMSeries()
    else:
      self.thereAreFilesInTheFolderFlag = 0

  def setlastNumberOfFiles(self,number):
    self.temp = number

  def getlastNumberOfFiles(self):
    return self.temp

  def createLoadableFileListFromSelection(self,selectedSeriesList,directory):

    # this function creates a DICOM filelist for all files in intraop directory.
    # It compares the names of the studies in seriesList to the
    # DICOM tag of the DICOM filelist and creates a new list of list loadable
    # list, where it puts together all DICOM files of one series into one list

    db=slicer.dicomDatabase

    # create dcmFileList that lists all .dcm files in directory
    if directory is not "":
      dcmFileList = []
      for dcm in os.listdir(directory):
        if len(dcm)-dcm.rfind('.dcm') == 4 and dcm != ".DS_Store":
          dcmFileList.append(directory+'/'+dcm)
        if dcm != ".DS_Store":
          dcmFileList.append(directory+'/'+dcm)

      self.selectedFileList=[]

      # write all selected files in selectedFileList
      for currentFile in dcmFileList:
       if db.fileValue(currentFile,self.SERIES_DESCRIPTION) in selectedSeriesList:
         self.selectedFileList.append(currentFile)

      # create a list with lists of files of each series in them
      self.loadableList=[]

      # add all found series to loadableList
      for series in selectedSeriesList:
        fileListOfSeries =[]
        for currentFile in self.selectedFileList:
          if db.fileValue(currentFile,self.SERIES_DESCRIPTION) == series:
            fileListOfSeries.append(currentFile)
        self.loadableList.append(fileListOfSeries)

  def loadSeriesIntoSlicer(self,selectedSeries,directory):

    self.createLoadableFileListFromSelection(selectedSeries,directory)

    for series in range(len(selectedSeries)):

      # get the filelist for the current series only
      files = self.loadableList[series]

      # create DICOMScalarVolumePlugin and load selectedSeries data from files into slicer
      scalarVolumePlugin = slicer.modules.dicomPlugins['DICOMScalarVolumePlugin']()

      try:
        loadables = scalarVolumePlugin.examine([files])

      except:
        print ('There is nothing to load. You have to select series')

      name = loadables[0].name
      v=scalarVolumePlugin.load(loadables[0])
      v.SetName(name)
      slicer.mrmlScene.AddNode(v)

    # return the last series to continue with segmentation
    return v

  def waitingForSeriesToBeCompleted(self):

    self.updatePatientSelectorFlag = False

    print ('**  new data in intraop directory detected **')
    print ('waiting 5 more seconds for the series to be completed')

    qt.QTimer.singleShot(5000,self.importDICOMSeries)

  def importDICOMSeries(self):

    self.newFileList= []
    self.seriesList= []
    self.selectableSeries=[]
    self.acqusitionTimes = {}
    indexer = ctk.ctkDICOMIndexer()
    db=slicer.dicomDatabase

    if self.thereAreFilesInTheFolderFlag == 1:
      self.newFileList=self.currentFileList
      self.thereAreFilesInTheFolderFlag = 0
    else:
      # create a List NewFileList that contains only new files in the intraop directory
      for item in os.listdir(self.directory):
        if item not in self.currentFileList:
          self.newFileList.append(item)

    # import file in DICOM database
    for currentFile in self.newFileList:
     if not currentFile == ".DS_Store":
       indexer.addFile(db,str(self.directory+'/'+currentFile),None)
       # print ('file '+str(file)+' was added by Indexer')

       # add Series to seriesList
       if db.fileValue(str(self.directory+'/'+currentFile),self.SERIES_DESCRIPTION) not in self.seriesList:
         importfile=str(self.directory+'/'+currentFile)
         self.seriesList.append(db.fileValue(importfile,self.SERIES_DESCRIPTION))

         # get acquisition time and save in dictionary
         acqTime=db.fileValue(importfile,self.ACQUISITION_TIME)[0:6]
         self.acqusitionTimes[str(db.fileValue(importfile,self.SERIES_DESCRIPTION))]= str(acqTime)


    indexer.addDirectory(db,str(self.directory))
    indexer.waitForImportFinished()

    # pass items from seriesList to selectableSeries to keep them in the right order
    for series in self.seriesList:
      if series not in self.selectableSeries:
        self.selectableSeries.append(series)

    # sort list by acquisition time
    self.selectableSeries=self.sortSeriesByAcquisitionTime(self.selectableSeries)

    # TODO: update GUI from here is not very nice. Find a way to call logic and get the self.selectableSeries
    # as a return

    slicer.modules.RegistrationModuleWidget.updateSeriesSelectorTable(self.selectableSeries)
    slicer.modules.RegistrationModuleWidget.patientCheckAfterImport(self.directory,self.newFileList)
    slicer.modules.RegistrationModuleWidget.checkTabAfterImport()

  def sortSeriesByAcquisitionTime(self,inputSeriesList):
    # this function sorts the self.acqusitionTimes
    # dictionary over its acquisiton times (values).
    # it returnes a sorted series list (keys) whereas
    # the 0th item is the earliest obtained series

    sortedList=sorted(self.acqusitionTimes, key=self.acqusitionTimes.get)
    return sortedList

  def removeEverythingInIntraopTestFolder(self):
    cmd=('rm -rfv '+slicer.modules.RegistrationModuleWidget.modulePath +'Resources/Testing/intraopDir/*')
    try:
      os.system(cmd)
    except:
      print ('DEBUG: could not delete files in '+self.modulePath+'Resources/Testing/intraopDir')

  def getNeedleTipAndTargetsPositions(self):

    # Get the fiducial lists
    fidNode1=slicer.mrmlScene.GetNodesByName('targets-BSPLINE').GetItemAsObject(0)
    fidNode2=slicer.mrmlScene.GetNodesByName('needle-tip').GetItemAsObject(0)

    # get the needleTip_position
    self.needleTip_position=[0.0,0.0,0.0]
    fidNode2.GetNthFiducialPosition(0,self.needleTip_position)

    # get the target position(s)
    number_of_targets=fidNode1.GetNumberOfFiducials()
    self.target_positions=[]

    for target in range(number_of_targets):
      target_position=[0.0,0.0,0.0]
      fidNode1.GetNthFiducialPosition(target,target_position)
      self.target_positions.append(target_position)

    print ('needleTip_position = '+str(self.needleTip_position))
    print ('target_positions are '+str(self.target_positions))

    return [self.needleTip_position,self.target_positions]

  def setNeedleTipPosition(self):

    if slicer.mrmlScene.GetNodesByName('needle-tip').GetItemAsObject(0) is None:

      # if needle tip is placed for the first time:

      # create Markups Node & display node to store needle tip position
      needleTipMarkupDisplayNode = slicer.vtkMRMLMarkupsDisplayNode()
      needleTipMarkupNode = slicer.vtkMRMLMarkupsFiducialNode()
      needleTipMarkupNode.SetName('needle-tip')
      slicer.mrmlScene.AddNode(needleTipMarkupDisplayNode)
      slicer.mrmlScene.AddNode(needleTipMarkupNode)
      needleTipMarkupNode.SetAndObserveDisplayNodeID(needleTipMarkupDisplayNode.GetID())

      # dont show needle tip in red Slice View
      needleNode=slicer.mrmlScene.GetNodesByName('needle-tip').GetItemAsObject(0)
      needleDisplayNode=needleNode.GetDisplayNode()
      needleDisplayNode.AddViewNodeID(slicer.modules.RegistrationModuleWidget.yellowSliceNode.GetID())

      # update the target table when markup was set
      needleTipMarkupNode.AddObserver(vtk.vtkCommand.ModifiedEvent,
                                      slicer.modules.RegistrationModuleWidget.updateTargetTable)

      # be sure to have the correct display node
      needleTipMarkupDisplayNode=slicer.mrmlScene.GetNodesByName('needle-tip').GetItemAsObject(0).GetDisplayNode()

      # Set visual fiducial attributes
      needleTipMarkupDisplayNode.SetTextScale(1.6)
      needleTipMarkupDisplayNode.SetGlyphScale(2.0)
      needleTipMarkupDisplayNode.SetGlyphType(12)
      #TODO: set color is somehow not working here
      needleTipMarkupDisplayNode.SetColor(1,1,50)

    else:
      # remove fiducial
      needleNode=slicer.mrmlScene.GetNodesByName('needle-tip').GetItemAsObject(0)
      needleNode.RemoveAllMarkups()

      # clear target table
      slicer.modules.RegistrationModuleWidget.clearTargetTable()

    # set active node ID and start place mode
    mlogic=slicer.modules.markups.logic()
    mlogic.SetActiveListID(slicer.mrmlScene.GetNodesByName('needle-tip').GetItemAsObject(0))
    slicer.modules.markups.logic().StartPlaceMode(0)

  def measureDistance(self,target_position,needleTip_position):

    # calculate 2D distance
    distance_2D_x=abs(target_position[0]-needleTip_position[0])
    distance_2D_y=abs(target_position[1]-needleTip_position[1])
    distance_2D_z=abs(target_position[2]-needleTip_position[2])

    # print ('distance_xRAS = '+str(distance_2D_x))
    # print ('distance_yRAS = '+str(distance_2D_y))
    # print ('distance_zRAS = '+str(distance_2D_z))

    # calculate 3D distance
    rulerNode=slicer.vtkMRMLAnnotationRulerNode()
    rulerNode.SetPosition1(target_position)
    rulerNode.SetPosition2(needleTip_position)
    distance_3D=rulerNode.GetDistanceMeasurement()

    return [distance_2D_x,distance_2D_y,distance_2D_z,distance_3D]

  def setupColorTable(self):

    # setup the PCampReview color table

    self.colorFile = (slicer.modules.RegistrationModuleWidget.modulePath + 'Resources/Colors/PCampReviewColors.csv')
    self.PCampReviewColorNode = slicer.vtkMRMLColorTableNode()
    colorNode = self.PCampReviewColorNode
    colorNode.SetName('PCampReview')
    slicer.mrmlScene.AddNode(colorNode)
    colorNode.SetTypeToUser()
    with open(self.colorFile) as f:
      n = sum(1 for line in f)
    colorNode.SetNumberOfColors(n-1)
    import csv
    self.structureNames = []
    with open(self.colorFile, 'rb') as csvfile:
      reader = csv.DictReader(csvfile, delimiter=',')
      for index,row in enumerate(reader):
        colorNode.SetColor(index,row['Label'],float(row['R'])/255,
                float(row['G'])/255,float(row['B'])/255,float(row['A']))
        self.structureNames.append(row['Label'])

  def hasImageData(self,volumeNode):
    """This is a dummy logic method that
    returns true if the passed in volume
    node has valid image data
    """
    if not volumeNode:
      print('no volume node')
      return False
    if volumeNode.GetImageData() is None:
      print('no image data')
      return False
    return True

  def takeScreenshot(self,name,description,layout=-1):
    # show the message even if not taking a screen shot
    self.delayDisplay(description)

    if self.enableScreenshots == 0:
      return

    lm = slicer.app.layoutManager()
    # switch on the type to get the requested window
    widget = 0
    if layout == slicer.qMRMLScreenShotDialog.FullLayout:
      # full layout
      widget = lm.viewport()
    elif layout == slicer.qMRMLScreenShotDialog.ThreeD:
      # just the 3D window
      widget = lm.threeDWidget(0).threeDView()
    elif layout == slicer.qMRMLScreenShotDialog.Red:
      # red slice window
      widget = lm.sliceWidget("Red")
    elif layout == slicer.qMRMLScreenShotDialog.Yellow:
      # yellow slice window
      widget = lm.sliceWidget("Yellow")
    elif layout == slicer.qMRMLScreenShotDialog.Green:
      # green slice window
      widget = lm.sliceWidget("Green")
    else:
      # default to using the full window
      widget = slicer.util.mainWindow()
      # reset the layout so that the node is set correctly
      layout = slicer.qMRMLScreenShotDialog.FullLayout

    # grab and convert to vtk image data
    qpixMap = qt.QPixmap().grabWidget(widget)
    qimage = qpixMap.toImage()
    imageData = vtk.vtkImageData()
    slicer.qMRMLUtils().qImageToVtkImageData(qimage,imageData)

    annotationLogic = slicer.modules.annotations.logic()
    annotationLogic.CreateSnapShot(name, description, layout, self.screenshotScaleFactor, imageData)

  def run(self):

    return True

  def runQuickSegmentationMode(self):

    # set four up view, select persistent fiducial marker as crosshair
    self.setVolumeClipUserMode()

    # let user place Fiducials
    self.placeFiducials()

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

  def updateModel(self,observer,caller):

    clipModelNode=slicer.mrmlScene.GetNodesByName('clipModelNode')
    self.clippingModel=clipModelNode.GetItemAsObject(0)

    inputMarkupNode=slicer.mrmlScene.GetNodesByName('inputMarkupNode')
    inputMarkup=inputMarkupNode.GetItemAsObject(0)

    import VolumeClipWithModel
    clipLogic=VolumeClipWithModel.VolumeClipWithModelLogic()
    clipLogic.updateModelFromMarkup(inputMarkup, self.clippingModel)

  def placeFiducials(self):

    # Create empty model node
    self.clippingModel = slicer.vtkMRMLModelNode()
    self.clippingModel.SetName('clipModelNode')
    slicer.mrmlScene.AddNode(self.clippingModel)

    # Create Display Node for Model
    clippingModelDisplayNode=slicer.vtkMRMLModelDisplayNode()
    clippingModelDisplayNode.SetSliceIntersectionThickness(3)
    clippingModelDisplayNode.SetColor((20,180,250))
    slicer.mrmlScene.AddNode(clippingModelDisplayNode)

    self.clippingModel.SetAndObserveDisplayNodeID(clippingModelDisplayNode.GetID())

    # Create markup display fiducials
    displayNode = slicer.vtkMRMLMarkupsDisplayNode()
    slicer.mrmlScene.AddNode(displayNode)

    # create markup fiducial node
    self.inputMarkup = slicer.vtkMRMLMarkupsFiducialNode()
    self.inputMarkup.SetName('inputMarkupNode')
    slicer.mrmlScene.AddNode(self.inputMarkup)
    self.inputMarkup.SetAndObserveDisplayNodeID(displayNode.GetID())

    # set Text Scale to 0
    inputMarkupDisplayNode=slicer.mrmlScene.GetNodesByName('inputMarkupNode').GetItemAsObject(0).GetDisplayNode()

    # Set Textscale
    inputMarkupDisplayNode.SetTextScale(0)

    # Set Glyph Size
    inputMarkupDisplayNode.SetGlyphScale(2.0)

    # Set Color
    inputMarkupDisplayNode.SetColor(0,0,0)

    # add Observer
    self.inputMarkup.AddObserver(vtk.vtkCommand.ModifiedEvent,self.updateModel)

  def modelToLabelmap(self,inputVolume,clippingModel):

    """
    PARAMETER FOR MODELTOLABELMAP CLI MODULE:
    Parameter (0/0): sampleDistance
    Parameter (0/1): labelValue
    Parameter (1/0): InputVolume
    Parameter (1/1): surface
    Parameter (1/2): OutputVolume
    """

    # initialize Label Map
    outputLabelMap=slicer.vtkMRMLScalarVolumeNode()
    outputLabelMap.SetLabelMap(1)
    name=(slicer.modules.RegistrationModuleWidget.referenceVolumeSelector.currentNode().GetName()+ '-label')
    outputLabelMap.SetName(name)
    slicer.mrmlScene.AddNode(outputLabelMap)

    if outputLabelMap:
      'outoutLabelMap is here!'

    # define params
    params = {'sampleDistance': 0.1, 'labelValue': 5, 'InputVolume' : inputVolume.GetID(),
              'surface' : clippingModel.GetID(), 'OutputVolume' : outputLabelMap.GetID()}

    print params
    # run ModelToLabelMap-CLI Module
    cliNode=slicer.cli.run(slicer.modules.modeltolabelmap, None, params, wait_for_completion=True)

    # use label contours
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeRed").SetUseLabelOutline(True)
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeYellow").SetUseLabelOutline(True)

    # rotate volume to plane
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeRed").RotateToVolumePlane(outputLabelMap)
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeYellow").RotateToVolumePlane(outputLabelMap)

    # set Layout to redSliceViewOnly
    lm=slicer.app.layoutManager()
    lm.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)

    # fit Slice View to FOV
    red=lm.sliceWidget('Red')
    redLogic=red.sliceLogic()
    redLogic.FitSliceToAll()

    # set Label Opacity Back
    redWidget = lm.sliceWidget('Red')
    compositNodeRed = redWidget.mrmlSliceCompositeNode()
    # compositNodeRed.SetLabelVolumeID(outputLabelMap.GetID())
    compositNodeRed.SetLabelOpacity(1)

    # remove markup fiducial node
    slicer.mrmlScene.RemoveNode(slicer.mrmlScene.GetNodesByName('clipModelNode').GetItemAsObject(0))

    # remove model node
    slicer.mrmlScene.RemoveNode(slicer.mrmlScene.GetNodesByName('inputMarkupNode').GetItemAsObject(0))

    print ('model to labelmap through')

    return outputLabelMap

  def BRAINSResample(self,inputVolume,referenceVolume,outputVolume,warpTransform):
    """
    Parameter (0/0): inputVolume
    Parameter (0/1): referenceVolume
    Parameter (1/0): outputVolume
    Parameter (1/1): pixelType
    Parameter (2/0): deformationVolume
    Parameter (2/1): warpTransform
    Parameter (2/2): interpolationMode
    Parameter (2/3): inverseTransform
    Parameter (2/4): defaultValue
    Parameter (3/0): gridSpacing
    Parameter (4/0): numberOfThreads
    """

    # define params
    params = {'inputVolume': inputVolume, 'referenceVolume': referenceVolume, 'outputVolume' : outputVolume,
              'warpTransform' : warpTransform,'interpolationMode' : 'NearestNeighbor'}

    print ('about to run BRAINSResample CLI with those params: ')
    print params
    # run ModelToLabelMap-CLI Module
    cliNode=slicer.cli.run(slicer.modules.brainsresample, None, params, wait_for_completion=True)
    print ('resample labelmap through')
    slicer.mrmlScene.AddNode(outputVolume)


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
    print (' ___ performing selfTest ___ ')
