import os
import datetime
import qt
import re
import slicer

from SlicerDevelopmentToolboxUtils.mixins import ModuleWidgetMixin


class NewCaseSelectionNameWidget(qt.QMessageBox, ModuleWidgetMixin):

  PREFIX = "Case"
  SUFFIX = "-" + datetime.date.today().strftime("%Y%m%d")
  SUFFIX_PATTERN = "-[0-9]{8}"
  CASE_NUMBER_DIGITS = 3
  PATTERN = PREFIX+"[0-9]{"+str(CASE_NUMBER_DIGITS-1)+"}[0-9]{1}"+SUFFIX_PATTERN

  def __init__(self, destination, parent=None):
    super(NewCaseSelectionNameWidget, self).__init__(parent)
    if not os.path.exists(destination):
      raise
    self.destinationRoot = destination
    self.newCaseDirectory = None
    self.minimum = self.getNextCaseNumber()
    self.setupUI()
    self.setupConnections()
    self.onCaseNumberChanged(self.minimum)

  def getNextCaseNumber(self):
    caseNumber = 0
    for dirName in [dirName for dirName in os.listdir(self.destinationRoot)
                     if os.path.isdir(os.path.join(self.destinationRoot, dirName)) and re.match(self.PATTERN, dirName)]:
      number = int(re.split(self.SUFFIX_PATTERN, dirName)[0].split(self.PREFIX)[1])
      caseNumber = caseNumber if caseNumber > number else number
    return caseNumber+1

  def setupUI(self):
    self.setWindowTitle("Case Number Selection")
    self.spinbox = qt.QSpinBox()
    self.spinbox.setRange(self.minimum, int("9"*self.CASE_NUMBER_DIGITS))

    self.hideInvisibleUnneededComponents()

    self.textLabel = qt.QLabel("Please select a case number for the new case.")
    self.textLabel.setStyleSheet("font-weight: bold;")
    self.previewLabel = qt.QLabel("New case directory:")
    self.preview = qt.QLabel()
    self.notice = qt.QLabel()
    self.notice.setStyleSheet("color:red;")

    self.okButton = self.addButton(self.Ok)
    self.okButton.enabled = False
    self.cancelButton = self.addButton(self.Cancel)
    self.setDefaultButton(self.okButton)

    self.groupBox = qt.QGroupBox()
    self.groupBox.setLayout(qt.QGridLayout())
    self.groupBox.layout().addWidget(self.textLabel, 0, 0, 1, 2)
    self.groupBox.layout().addWidget(qt.QLabel("Proposed Case Number"), 1, 0)
    self.groupBox.layout().addWidget(self.spinbox, 1, 1)
    self.groupBox.layout().addWidget(self.previewLabel, 2, 0, 1, 2)
    self.groupBox.layout().addWidget(self.preview, 3, 0, 1, 2)
    self.groupBox.layout().addWidget(self.notice, 4, 0, 1, 2)

    self.groupBox.layout().addWidget(self.okButton, 5, 0)
    self.groupBox.layout().addWidget(self.cancelButton, 5, 1)

    self.layout().addWidget(self.groupBox, 1, 1)

  def hideInvisibleUnneededComponents(self):
    for oName in ["qt_msgbox_label", "qt_msgboxex_icon_label"]:
      try:
        slicer.util.findChild(self, oName).hide()
      except RuntimeError:
        pass

  def setupConnections(self):
    self.spinbox.valueChanged.connect(self.onCaseNumberChanged)

  def onCaseNumberChanged(self, caseNumber):
    formatString = '%0'+str(self.CASE_NUMBER_DIGITS)+'d'
    caseNumber = formatString % caseNumber
    directory = self.PREFIX+caseNumber+self.SUFFIX
    self.newCaseDirectory = os.path.join(self.destinationRoot, directory)
    self.preview.setText( self.newCaseDirectory)
    self.okButton.enabled = not os.path.exists(self.newCaseDirectory)
    self.notice.text = "" if not os.path.exists(self.newCaseDirectory) else "Note: Directory already exists."

