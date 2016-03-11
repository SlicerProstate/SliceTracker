import qt
import vtk


class SliceAnnotation(object):

  ALIGN_LEFT = "left"
  ALIGN_CENTER = "center"
  ALIGN_RIGHT = "right"
  ALIGN_TOP = "top"
  ALIGN_BOTTOM = "bottom"
  POSSIBLE_VERTICAL_ALIGN = [ALIGN_TOP, ALIGN_CENTER, ALIGN_BOTTOM]
  POSSIBLE_HORIZONTAL_ALIGN = [ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT]

  @property
  def fontSize(self):
    return self._fontSize

  @fontSize.setter
  def fontSize(self, size):
    self._fontSize = size
    if self.textProperty:
      self.textProperty.SetFontSize(self.fontSize)
      self.textActor.SetTextProperty(self.textProperty)
    self.update()

  @property
  def textProperty(self):
    if not self.textActor:
      return None
    return self.textActor.GetTextProperty()

  @textProperty.setter
  def textProperty(self, textProperty):
    assert issubclass(textProperty, vtk.vtkTextProperty)
    self.textActor.SetTextProperty(textProperty)
    self.update()

  @property
  def opacity(self):
    if self.textProperty:
      return self.textProperty.GetOpacity()
    return None

  @opacity.setter
  def opacity(self, value):
    if not self.textProperty:
      return
    self.textProperty.SetOpacity(value)
    self.update()

  @property
  def color(self):
    if self.textProperty:
      return self.textProperty.GetColor()

  @color.setter
  def color(self, value):
    assert type(value) is tuple and len(value) == 3
    if self.textProperty:
      self.textProperty.SetColor(value)
      self.update()

  @property
  def verticalAlign(self):
    return self._verticalAlign

  @verticalAlign.setter
  def verticalAlign(self, value):
    if value not in self.POSSIBLE_VERTICAL_ALIGN:
      raise ValueError("Value %s is not allowed for vertical alignment. Only the following values are allowed: %s"
                       % (str(value), str(self.POSSIBLE_VERTICAL_ALIGN)))
    else:
      self._verticalAlign = value

  @property
  def horizontalAlign(self):
    return self._horizontalAlign

  @horizontalAlign.setter
  def horizontalAlign(self, value):
    if value not in self.POSSIBLE_HORIZONTAL_ALIGN:
      raise ValueError("Value %s is not allowed for horizontal alignment. Only the following values are allowed: %s"
                       % (str(value), str(self.POSSIBLE_HORIZONTAL_ALIGN)))
    else:
      self._horizontalAlign = value

  @property
  def renderer(self):
    return self.sliceView.renderWindow().GetRenderers().GetItemAsObject(0)

  def __init__(self, widget, text, **kwargs):
    self.observer = None
    self.textActor = None
    self.text = text

    self.sliceWidget = widget
    self.sliceView = widget.sliceView()
    self.sliceLogic = widget.sliceLogic()
    self.sliceNode = self.sliceLogic.GetSliceNode()
    self.sliceNodeDimensions = self.sliceNode.GetDimensions()

    self.xPos = kwargs.pop('xPos', 0)
    self.yPos = kwargs.pop('yPos', 0)

    self.initialFontSize = kwargs.pop('fontSize', 20)
    self.fontSize = self.initialFontSize
    self.textColor = kwargs.pop('color', (1, 0, 0))
    self.textBold = kwargs.pop('bold', 1)
    self.textShadow = kwargs.pop('shadow', 1)
    self.textOpacity = kwargs.pop('opacity', 1.0)
    self.verticalAlign = kwargs.pop('verticalAlign', 'center')
    self.horizontalAlign = kwargs.pop('horizontalAlign', 'center')

    self.createTextActor()

  def remove(self):
    self._removeObserver()
    self._removeActor()
    self.sliceView.update()

  def _addObserver(self):
    if not self.observer and self.sliceNode:
      self.observer = self.sliceNode.AddObserver(vtk.vtkCommand.ModifiedEvent, self.modified)

  def _removeObserver(self):
    if self.observer:
      self.sliceNode.RemoveObserver(self.observer)
      self.observer = None

  def _removeActor(self):
    try:
      self.renderer.RemoveActor(self.textActor)
    except:
      pass

  def _addActor(self):
    self.renderer.AddActor(self.textActor)
    self.update()

  def update(self):
    self.sliceView.update()

  def createTextActor(self):
    self.textActor = vtk.vtkTextActor()
    self.textActor.SetInput(self.text)
    self.textProperty.SetFontSize(self.fontSize)
    self.textProperty.SetColor(self.textColor)
    self.textProperty.SetBold(self.textBold)
    self.textProperty.SetShadow(self.textShadow)
    self.textProperty.SetOpacity(self.textOpacity)
    self.textActor.SetTextProperty(self.textProperty)
    self.fitIntoViewport()
    self._addActor()
    self._addObserver()

  def applyPositioning(self):
    xPos = self.applyHorizontalAlign()
    yPos = self.applyVerticalAlign()
    self.textActor.SetDisplayPosition(xPos, yPos)

  def applyHorizontalAlign(self):
    centerX = int((self.sliceView.width - self.getFontWidth()) / 2)
    if self.xPos:
      xPos = self.xPos if 0 < self.xPos < centerX else centerX
    else:
      if self.horizontalAlign == self.ALIGN_LEFT:
        xPos = 0
      elif self.horizontalAlign == self.ALIGN_CENTER:
        xPos = centerX
      elif self.horizontalAlign == self.ALIGN_RIGHT:
        xPos = self.sliceView.width - self.getFontWidth()
    return int(xPos)

  def applyVerticalAlign(self):
    centerY = int((self.sliceView.height - self.getFontHeight()) / 2)
    if self.yPos:
      yPos = self.yPos if 0 < self.yPos < centerY else centerY
    else:
      if self.verticalAlign == self.ALIGN_TOP:
        yPos = self.sliceView.height - self.getFontHeight()
      elif self.verticalAlign == self.ALIGN_CENTER:
        yPos = centerY
      elif self.verticalAlign == self.ALIGN_BOTTOM:
        yPos = 0
    return int(yPos)

  def modified(self, observee, event):
    if event != "ModifiedEvent":
      return
    currentDimensions = observee.GetDimensions()
    if currentDimensions != self.sliceNodeDimensions:
      self.fitIntoViewport()
      self.update()
      self.sliceNodeDimensions = currentDimensions

  def getFontWidth(self):
    return self.getFontDimensions()[0]

  def getFontHeight(self):
    return self.getFontDimensions()[1]

  def getFontDimensions(self):
    size = [0.0, 0.0]
    self.textActor.GetSize(self.renderer, size)
    return size

  def fitIntoViewport(self):
    while self.getFontWidth() < self.sliceView.width and self.fontSize < self.initialFontSize:
      self.fontSize += 1
    while self.getFontWidth() > self.sliceView.width:
      self.fontSize -= 1
    self.applyPositioning()


class ExtendedQMessageBox(qt.QMessageBox):

  def __init__(self, parent= None):
    super(ExtendedQMessageBox, self).__init__(parent)
    self.setupUI()

  def setupUI(self):
    self.checkbox = qt.QCheckBox("Remember the selection and do not notify again")
    self.layout().addWidget(self.checkbox, 1,2)

  def exec_(self, *args, **kwargs):
    return qt.QMessageBox.exec_(self, *args, **kwargs), self.checkbox.isChecked()