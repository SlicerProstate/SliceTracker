import logging
import slicer, vtk
import os, json
import shutil
from collections import OrderedDict

from SlicerDevelopmentToolboxUtils.constants import FileExtension
from SlicerDevelopmentToolboxUtils.mixins import ModuleLogicMixin
from SlicerDevelopmentToolboxUtils.decorators import onExceptionReturnNone, logmethod
from SlicerDevelopmentToolboxUtils.widgets import CustomStatusProgressbar

from helpers import SeriesTypeManager


class SessionData(ModuleLogicMixin):

  NewResultCreatedEvent = vtk.vtkCommand.UserEvent + 901

  DEFAULT_JSON_FILE_NAME = "results.json"

  _completed = False
  _resumed = False

  @property
  def completed(self):
    return self._completed

  @completed.setter
  def completed(self, value):
    self._completed = value
    self.completedLogTimeStamp = self.generateLogfileTimeStampDict() if self._completed else None

  @property
  def resumed(self):
    return self._resumed

  @resumed.setter
  def resumed(self, value):
    if value and self.completed:
      raise ValueError("Completed case is not supposed to be resumed.")
    if value and not self.completed:
      self.resumeTimeStamps.append(self.getTime())
    self._resumed = value

  @staticmethod
  def wasSessionCompleted(filename):
    with open(filename) as data_file:
      data = json.load(data_file)
      procedureEvents = data["procedureEvents"]
      return "caseCompleted" in procedureEvents.keys()

  def __init__(self):
    self.resetAndInitializeData()

  def resetAndInitializeData(self):
    self.seriesTypeManager = SeriesTypeManager()
    self.startTimeStamp = self.getTime()
    self.resumeTimeStamps = []
    self.closedLogTimeStamps = []

    self.completed = False
    self.usePreopData = False
    self.biasCorrectionDone = False

    self.clippingModelNode = None
    self.inputMarkupNode = None

    self.initialVolume = None
    self.initialLabel = None
    self.initialTargets = None
    self.initialTargetsPath = None

    self.zFrameRegistrationResult = None

    self._savedRegistrationResults = []
    self.initializeRegistrationResults()

    self.customProgressBar = CustomStatusProgressbar()

  def initializeRegistrationResults(self):
    self.registrationResults = OrderedDict()

  def createZFrameRegistrationResult(self, series):
    self.zFrameRegistrationResult = ZFrameRegistrationResult(series)
    return self.zFrameRegistrationResult

  def createResult(self, series, invokeEvent=True):
    assert series not in self.registrationResults.keys()
    self.registrationResults[series] = RegistrationResult(series)
    if invokeEvent is True:
      self.invokeEvent(self.NewResultCreatedEvent, series)
    return self.registrationResults[series]

  def readProcedureEvents(self, procedureEvents):
    self.startTimeStamp = procedureEvents["caseStarted"]
    self.completed = "caseCompleted" in procedureEvents.keys()
    if self.completed:
      self.completedLogTimeStamp = procedureEvents["caseCompleted"]
    if "caseClosed" in procedureEvents.keys():
      self.closedLogTimeStamps = procedureEvents["caseClosed"]
    if "caseResumed" in procedureEvents.keys():
      self.resumeTimeStamps = procedureEvents["caseResumed"]

  def load(self, filename):
    directory = os.path.dirname(filename)
    self.resetAndInitializeData()
    self.alreadyLoadedFileNames = {}
    with open(filename) as data_file:
      self.customProgressBar.visible = True
      self.customProgressBar.text = "Reading meta information"
      logging.debug("reading json file %s" % filename)
      data = json.load(data_file)

      self.readProcedureEvents(data["procedureEvents"])

      self.usePreopData = data["usedPreopData"]
      self.biasCorrectionDone = data["biasCorrected"]

      if "initialTargets" in data.keys():
        self.initialTargets = self._loadOrGetFileData(directory,
                                                      data["initialTargets"], slicer.util.loadMarkupsFiducialList)
        self.initialTargetsPath = os.path.join(directory, data["initialTargets"])

      if "zFrameRegistration" in data.keys():
        zFrameRegistration = data["zFrameRegistration"]
        volume = self._loadOrGetFileData(directory, zFrameRegistration["volume"], slicer.util.loadVolume)
        transform = self._loadOrGetFileData(directory, zFrameRegistration["transform"], slicer.util.loadTransform)
        name = zFrameRegistration["name"] if zFrameRegistration.has_key("name") else volume.GetName()
        self.zFrameRegistrationResult = ZFrameRegistrationResult(name)
        self.zFrameRegistrationResult.volume = volume
        self.zFrameRegistrationResult.transform = transform
        if zFrameRegistration["seriesType"]:
          self.seriesTypeManager.assign(self.zFrameRegistrationResult.name, zFrameRegistration["seriesType"])

      if "initialVolume" in data.keys():
        self.initialVolume = self._loadOrGetFileData(directory, data["initialVolume"], slicer.util.loadVolume)

      self.loadResults(data, directory)
    self.registrationResults = OrderedDict(sorted(self.registrationResults.items()))  # TODO: sort here?
    return True

  def loadResults(self, data, directory):
    if len(data["results"]):
      self.customProgressBar.maximum = len(data["results"])
    for index, jsonResult in enumerate(data["results"], start=1):
      name = jsonResult["name"]
      logging.debug("processing %s" % name)
      result = self.createResult(name, invokeEvent=False)
      self.customProgressBar.updateStatus("Loading series registration result %s" % result.name, index)
      slicer.app.processEvents()

      for attribute, value in jsonResult.iteritems():
        logging.debug("found %s: %s" % (attribute, value))
        if attribute == 'volumes':
          self._loadResultFileData(value, directory, slicer.util.loadVolume, result.setVolume)
        elif attribute == 'transforms':
          self._loadResultFileData(value, directory, slicer.util.loadTransform, result.setTransform)
        elif attribute == 'targets':
          approved = value.pop('approved', None)
          original = value.pop('original', None)
          self._loadResultFileData(value, directory, slicer.util.loadMarkupsFiducialList, result.setTargets)
          if approved:
            approvedTargets = self._loadOrGetFileData(directory, approved["fileName"], slicer.util.loadMarkupsFiducialList)
            setattr(result.targets, 'approved', approvedTargets)
            result.targets.modifiedTargets[jsonResult["registrationType"]] = approved["userModified"]
          if original:
            originalTargets = self._loadOrGetFileData(directory, original, slicer.util.loadMarkupsFiducialList)
            setattr(result.targets, 'original', originalTargets)
        elif attribute == 'labels':
          self._loadResultFileData(value, directory, slicer.util.loadLabelVolume, result.setLabel)
        elif attribute == 'status':
          result.status = value["state"]
          result.timestamp = value["time"]
        elif attribute == 'seriesType':
          seriesType = jsonResult["seriesType"] if jsonResult.has_key("seriesType") else None
          self.seriesTypeManager.assign(name, seriesType)
        else:
          setattr(result, attribute, value)
        self.customProgressBar.text = "Finished loading registration results"

  def _loadResultFileData(self, dictionary, directory, loadFunction, setFunction):
    for regType, filename in dictionary.iteritems():
      data = self._loadOrGetFileData(directory, filename, loadFunction)
      setFunction(regType, data)

  def _loadOrGetFileData(self, directory, filename, loadFunction):
    if not filename:
      return None
    try:
      data = self.alreadyLoadedFileNames[filename]
    except KeyError:
      _, data = loadFunction(os.path.join(directory, filename), returnNode=True)
      self.alreadyLoadedFileNames[filename] = data
    return data

  def generateLogfileTimeStampDict(self):
    return {
      "time": self.getTime(),
      "logfile": os.path.basename(self.getSlicerErrorLogPath())
    }

  def close(self, outputDir):
    if not self.completed:
      self.closedLogTimeStamps.append(self.generateLogfileTimeStampDict())
    return self.save(outputDir)

  def save(self, outputDir):
    if not os.path.exists(outputDir):
      self.createDirectory(outputDir)

    successfullySavedFileNames = []
    failedSaveOfFileNames = []

    logFilePath = self.getSlicerErrorLogPath()
    shutil.copy(logFilePath, os.path.join(outputDir, os.path.basename(logFilePath)))
    successfullySavedFileNames.append(os.path.join(outputDir, os.path.basename(logFilePath)))

    def saveManualSegmentation():
      if self.clippingModelNode:
        success, name = self.saveNodeData(self.clippingModelNode, outputDir, FileExtension.VTK, overwrite=True)
        self.handleSaveNodeDataReturn(success, name, successfullySavedFileNames, failedSaveOfFileNames)

      if self.inputMarkupNode:
        success, name = self.saveNodeData(self.inputMarkupNode, outputDir, FileExtension.FCSV, overwrite=True)
        self.handleSaveNodeDataReturn(success, name, successfullySavedFileNames, failedSaveOfFileNames)

    def saveInitialTargets():
      success, name = self.saveNodeData(self.initialTargets, outputDir, FileExtension.FCSV,
                                        name="Initial_Targets", overwrite=True)
      self.handleSaveNodeDataReturn(success, name, successfullySavedFileNames, failedSaveOfFileNames)
      return name + FileExtension.FCSV

    def saveInitialVolume():
      success, name = self.saveNodeData(self.initialVolume, outputDir, FileExtension.NRRD, overwrite=True)
      self.handleSaveNodeDataReturn(success, name, successfullySavedFileNames, failedSaveOfFileNames)
      return name + FileExtension.NRRD

    def createResultsList():
      results = []
      for result in sorted(self.getResultsAsList(), key=lambda r: r.seriesNumber):
        results.append(result.asDict())
      return results

    saveManualSegmentation()

    data = {
      "usedPreopData": self.usePreopData,
      "biasCorrected": self.biasCorrectionDone,
      "results": createResultsList()
    }

    def addProcedureEvents():
      procedureEvents = {
        "caseStarted": self.startTimeStamp,
      }
      if len(self.closedLogTimeStamps):
        procedureEvents["caseClosed"] = self.closedLogTimeStamps
      if len(self.resumeTimeStamps):
        procedureEvents["caseResumed"] = self.resumeTimeStamps
      if self.completed:
        procedureEvents["caseCompleted"] = self.completedLogTimeStamp
      data["procedureEvents"] = procedureEvents

    addProcedureEvents()

    if self.zFrameRegistrationResult:
      data["zFrameRegistration"] = self.zFrameRegistrationResult.save(outputDir)

    if self.initialTargets:
      data["initialTargets"] = saveInitialTargets()

    if self.initialVolume:
      data["initialVolume"] = saveInitialVolume()

    destinationFile = os.path.join(outputDir, self.DEFAULT_JSON_FILE_NAME)
    with open(destinationFile, 'w') as outfile:
      logging.debug("Writing registration results to %s" % destinationFile)
      json.dump(data, outfile, indent=2)

    failedSaveOfFileNames += self.saveRegistrationResults(outputDir)

    self.printOutput("The following data was successfully saved:\n", successfullySavedFileNames)
    self.printOutput("The following data failed to saved:\n", failedSaveOfFileNames)
    return (len(failedSaveOfFileNames) == 0, failedSaveOfFileNames)

  def printOutput(self, message, fileNames):
    if not len(fileNames):
      return
    for fileName in fileNames:
      message += fileName + "\n"
    logging.debug(message)

  @logmethod(level=logging.INFO)
  def saveRegistrationResults(self, outputDir):
    failedToSave = []
    self.customProgressBar.visible = True
    for index, result in enumerate(self.getResultsAsList(), start=1):
      self.customProgressBar.maximum = len(self.registrationResults)
      self.customProgressBar.updateStatus("Saving registration result for series %s" % result.name, index)
      slicer.app.processEvents()
      print self._savedRegistrationResults
      if result not in self._savedRegistrationResults:
        successfulList, failedList = result.save(outputDir)
        failedToSave += failedList
        self._savedRegistrationResults.append(result)
    self.customProgressBar.text = "Registration data successfully saved" if len(failedToSave) == 0 else "Error/s occurred during saving"
    return failedToSave

  def _registrationResultHasStatus(self, series, status, method=all):
    if not type(series) is int:
      series = RegistrationResult.getSeriesNumberFromString(series)
    results = self.getResultsBySeriesNumber(series)
    return method(result.status == status for result in results) if len(results) else False

  def registrationResultWasApproved(self, series):
    return self._registrationResultHasStatus(series, RegistrationStatus.APPROVED_STATUS, method=any)

  def registrationResultWasSkipped(self, series):
    return self._registrationResultHasStatus(series, RegistrationStatus.SKIPPED_STATUS)

  def registrationResultWasRejected(self, series):
    return self._registrationResultHasStatus(series, RegistrationStatus.REJECTED_STATUS)

  def registrationResultWasApprovedOrRejected(self, series):
    return self._registrationResultHasStatus(series, RegistrationStatus.REJECTED_STATUS) or \
           self._registrationResultHasStatus(series, RegistrationStatus.APPROVED_STATUS)

  def getResultsAsList(self):
    return self.registrationResults.values()

  def getMostRecentApprovedCoverProstateRegistration(self):
    seriesTypeManager = SeriesTypeManager()
    for result in self.registrationResults.values():
      if seriesTypeManager.isCoverProstate(result.name) and result.approved:
        return result
    return None

  def getLastApprovedRigidTransformation(self):
    if sum([1 for result in self.registrationResults.values() if result.approved]) == 1:
      lastRigidTfm = None
    else:
      lastRigidTfm = self.getMostRecentApprovedResult().transforms.rigid
    if not lastRigidTfm:
      lastRigidTfm = slicer.vtkMRMLLinearTransformNode()
      slicer.mrmlScene.AddNode(lastRigidTfm)
    return lastRigidTfm

  @onExceptionReturnNone
  def getMostRecentApprovedTransform(self):
    seriesTypeManager = SeriesTypeManager()
    results = sorted(self.registrationResults.values(), key=lambda s: s.seriesNumber)
    for result in reversed(results):
      if result.approved and not seriesTypeManager.isCoverProstate(result.name):
        return result.getTransform(result.registrationType)
    return None

  @onExceptionReturnNone
  def getResult(self, series):
    return self.registrationResults[series]

  def getResultsBySeries(self, series):
    seriesNumber = RegistrationResult.getSeriesNumberFromString(series)
    return self.getResultsBySeriesNumber(seriesNumber)

  def getResultsBySeriesNumber(self, seriesNumber):
    return [result for result in self.getResultsAsList() if seriesNumber == result.seriesNumber]

  def removeResult(self, series):
    # TODO: is this method ever used?
    try:
      del self.registrationResults[series]
    except KeyError:
      pass

  def exists(self, series):
    return series in self.registrationResults.keys()

  @onExceptionReturnNone
  def getMostRecentApprovedResult(self, priorToSeriesNumber=None):
    results = sorted(self.registrationResults.values(), key=lambda s: s.seriesNumber)
    if priorToSeriesNumber:
      results = [result for result in results if result.seriesNumber < priorToSeriesNumber]
    for result in reversed(results):
      if result.approved:
        return result
    return None

  def getApprovedOrLastResultForSeries(self, series):
    results = self.getResultsBySeries(series)
    for result in results:
      if result.approved:
        return result
    return results[-1]


class AbstractRegistrationData(ModuleLogicMixin):

  FILE_EXTENSION = None

  def __init__(self):
    self.initializeMembers()

  def initializeMembers(self):
    raise NotImplementedError

  def asList(self):
    raise NotImplementedError

  def asDict(self):
    raise NotImplementedError

  @onExceptionReturnNone
  def getFileName(self, node):
    return self.replaceUnwantedCharacters(node.GetName()) + self.FILE_EXTENSION

  def getFileNameByAttributeName(self, name):
    return self.getFileName(getattr(self, name))

  # @logmethod(level=logging.INFO)
  def getAllFileNames(self):
    fileNames = {}
    for regType, node in self.asDict().iteritems():
      if node:
        fileNames[regType] = self.getFileName(node)
    return fileNames

  # @logmethod(level=logging.INFO)
  def save(self, directory):
    assert self.FILE_EXTENSION is not None
    savedSuccessfully = []
    failedToSave = []
    for node in [node for node in self.asList() if node]:
      success, name = self.saveNodeData(node, directory, self.FILE_EXTENSION)
      self.handleSaveNodeDataReturn(success, name, savedSuccessfully, failedToSave)
    return savedSuccessfully, failedToSave


class RegistrationTypeData(AbstractRegistrationData):

  RegistrationTypes = ['rigid', 'affine', 'bSpline']

  def __init__(self):
    super(RegistrationTypeData, self).__init__()

  def initializeMembers(self):
    self.rigid = None
    self.affine = None
    self.bSpline = None

  def asList(self):
    return [self.rigid, self.affine, self.bSpline]

  def asDict(self):
    return {'rigid': self.rigid, 'affine': self.affine, 'bSpline': self.bSpline}


class Transforms(RegistrationTypeData):

  FILE_EXTENSION = FileExtension.H5

  def __init__(self):
    super(Transforms, self).__init__()


class Targets(RegistrationTypeData):

  FILE_EXTENSION = FileExtension.FCSV

  def __init__(self):
    super(Targets, self).__init__()

  def initializeMembers(self):
    super(Targets, self).initializeMembers()
    self.modifiedTargets = {}
    self.original = None
    self.approved = None

  def asList(self):
    return super(Targets, self).asList() + [self.original, self.approved]

  def asDict(self):
    dictionary = super(Targets, self).asDict()
    dictionary.update({'original':self.original, 'approved': self.approved})
    return dictionary

  def approve(self, registrationType):
    approvedTargets = getattr(self, registrationType)
    self.approved = self.cloneFiducials(approvedTargets,
                                        cloneName=approvedTargets.GetName().replace(registrationType, "approved"),
                                        keepDisplayNode=True)

  def save(self, directory):
    savedSuccessfully, failedToSave = super(Targets, self).save(directory)
    if self.approved:
      success, name = self.saveNodeData(self.approved, directory, self.FILE_EXTENSION)
      self.handleSaveNodeDataReturn(success, name, savedSuccessfully, failedToSave)
    return savedSuccessfully, failedToSave

  def isGoingToBeMoved(self, targetList, index):
    assert targetList in self.asList()
    regType = self.getRegistrationTypeForTargetList(targetList)
    if not self.modifiedTargets.has_key(regType):
      self.modifiedTargets[regType] = [False for i in range(targetList.GetNumberOfFiducials())]
    self.modifiedTargets[regType][index] = True

  def getRegistrationTypeForTargetList(self, targetList):
    for regType, currentTargetList in self.asDict().iteritems():
      if targetList is currentTargetList:
        return regType
    return None


class Volumes(RegistrationTypeData):

  FILE_EXTENSION = FileExtension.NRRD

  def __init__(self):
    super(Volumes, self).__init__()

  def initializeMembers(self):
    super(Volumes, self).initializeMembers()
    self.fixed = None
    self.moving = None

  def asList(self):
    return super(Volumes, self).asList() + [self.fixed, self.moving]

  def asDict(self):
    dictionary = super(Volumes, self).asDict()
    dictionary.update({'fixed':self.fixed, 'moving': self.moving})
    return dictionary


class Labels(AbstractRegistrationData):

  FILE_EXTENSION = FileExtension.NRRD

  def __init__(self):
    super(Labels, self).__init__()

  def initializeMembers(self):
    self.moving = None
    self.fixed = None

  def asList(self):
    return [self.fixed, self.moving]

  def asDict(self):
    return {'fixed':self.fixed, 'moving':self.moving}


class RegistrationStatus(ModuleLogicMixin):

  SkippedEvent = vtk.vtkCommand.UserEvent + 601
  ApprovedEvent = vtk.vtkCommand.UserEvent + 602
  RejectedEvent = vtk.vtkCommand.UserEvent + 603

  UNDEFINED_STATUS = 'undefined'
  SKIPPED_STATUS = 'skipped'
  APPROVED_STATUS = 'approved'
  REJECTED_STATUS = 'rejected'

  __allowedStates = [SKIPPED_STATUS, APPROVED_STATUS, REJECTED_STATUS]
  StatusEvents = {SKIPPED_STATUS: SKIPPED_STATUS, APPROVED_STATUS: ApprovedEvent, REJECTED_STATUS: RejectedEvent}

  @property
  def status(self):
    return self._status

  @status.setter
  def status(self, value):
    assert value in self.__allowedStates
    self.timestamp = self.getTime()
    self._status = value
    self.invokeEvent(self.StatusEvents[value])

  @property
  def approved(self):
    return self.hasStatus(self.APPROVED_STATUS)

  @property
  def skipped(self):
    return self.hasStatus(self.SKIPPED_STATUS)

  @property
  def rejected(self):
    return self.hasStatus(self.REJECTED_STATUS)

  def __init__(self):
    self._status = self.UNDEFINED_STATUS

  def hasStatus(self, status):
    return self.status == status

  def wasEvaluated(self):
    return self.status in [self.SKIPPED_STATUS, self.APPROVED_STATUS, self.REJECTED_STATUS]

  def approve(self):
    self.status = self.APPROVED_STATUS

  def skip(self):
    self.status = self.SKIPPED_STATUS

  def reject(self):
    self.status = self.REJECTED_STATUS

  def asDict(self):
    return {
      "status": {
        "state": self.status,
        "time": self.timestamp
      }
    }


class RegistrationResultBase(ModuleLogicMixin):

  @property
  def name(self):
    return self._name

  @name.setter
  def name(self, name):
    splitted = name.split(': ')
    assert len(splitted) == 2
    self._name = name
    self._seriesNumber = int(splitted[0])
    self._seriesDescription = splitted[1]

  @property
  def seriesNumber(self):
    return self._seriesNumber

  @property
  def seriesDescription(self):
    return self._seriesDescription

  @property
  def seriesType(self):
    seriesTypeManager = SeriesTypeManager()
    return seriesTypeManager.getSeriesType(self.name)

  def __init__(self, series):
    self.name = series


class RegistrationResult(RegistrationResultBase, RegistrationStatus):

  REGISTRATION_TYPE_NAMES = ['rigid', 'affine', 'bSpline']

  @staticmethod
  def getSeriesNumberFromString(text):
    return int(text.split(": ")[0])

  @property
  @onExceptionReturnNone
  def approvedVolume(self):
    return self.getVolume(self.registrationType)

  @property
  def targetsWereModified(self):
    return len(self.targets.modifiedTargets) > 0

  @property
  def cmdFileName(self):
    return str(self.seriesNumber) + "-CMD-PARAMETERS" + self.suffix + FileExtension.TXT

  def __init__(self, series):
    RegistrationStatus.__init__(self)
    RegistrationResultBase.__init__(self, series)

    self.receivedTimestamp = self.getTime()

    self.volumes = Volumes()
    self.transforms = Transforms()
    self.targets = Targets()
    self.labels = Labels()

    self.cmdArguments = ""
    self.suffix = ""
    self.score = None

    self.modifiedTargets = {}

    self.registrationType = None

  def setVolume(self, name, volume):
    setattr(self.volumes, name, volume)

  def getVolume(self, name):
    return getattr(self.volumes, name)

  def setTransform(self, name, transform):
    setattr(self.transforms, name, transform)

  def getTransform(self, name):
    return getattr(self.transforms, name)

  def setTargets(self, name, targets):
    setattr(self.targets, name, targets)

  def getLabel(self, name):
    return getattr(self.labels, name)

  def setLabel(self, name, label):
    setattr(self.labels, name, label)

  def getTargets(self, name):
    return getattr(self.targets, name)

  def approve(self, registrationType):
    assert registrationType in self.REGISTRATION_TYPE_NAMES
    self.registrationType = registrationType
    self.targets.approve(registrationType)
    RegistrationStatus.approve(self)

  def printSummary(self):
    logging.debug('# ___________________________  registration output  ________________________________')
    logging.debug(self.__dict__)
    logging.debug('# __________________________________________________________________________________')

  @logmethod(logging.INFO)
  def save(self, outputDir):
    def saveCMDParameters():
      if self.cmdArguments != "":
        filename = os.path.join(outputDir, self.cmdFileName)
        f = open(filename, 'w+')
        f.write(self.cmdArguments)
        f.close()

    def saveData():
      savedSuccessfully = []
      failedToSave = []
      for data in [self.transforms, self.targets, self.volumes, self.labels]:
        successful, failed = data.save(outputDir)
        savedSuccessfully += successful
        failedToSave += failed
      logging.debug("Successfully saved: %s \n" % str(savedSuccessfully))
      logging.debug("Failed to save: %s \n" % str(failedToSave))
      return savedSuccessfully, failedToSave

    saveCMDParameters()
    return saveData()

  def getApprovedTargetsModifiedStatus(self):
    try:
      modified = self.targets.modifiedTargets[self.registrationType]
    except KeyError:
      modified = [False for i in range(self.targets.approved.GetNumberOfFiducials())]
    return modified

  def asDict(self):
    seriesTypeManager = SeriesTypeManager()
    dictionary = super(RegistrationResult, self).asDict()
    dictionary.update({
      "name": self.name,
      "seriesType": seriesTypeManager.getSeriesType(self.name),
      "receivedTime": self.receivedTimestamp
    })
    if self.approved or self.rejected:
      dictionary["targets"] = self.targets.getAllFileNames()
      dictionary["transforms"] = self.transforms.getAllFileNames()
      dictionary["volumes"] = self.volumes.getAllFileNames()
      dictionary["labels"] = self.labels.getAllFileNames()
      dictionary["suffix"] = self.suffix
      if self.approved:
        dictionary["registrationType"] = self.registrationType
    elif self.skipped:
      dictionary["volumes"] = {
        "fixed": self.volumes.getFileName(self.volumes.fixed)
      }
    if self.score:
      dictionary["score"] = self.score
    if self.approved:
      dictionary["targets"]["approved"] = {
        "userModified": self.getApprovedTargetsModifiedStatus(),
        "fileName": self.targets.getFileNameByAttributeName("approved")
      }
    return dictionary


class ZFrameRegistrationResult(RegistrationResultBase):

  def __init__(self, series):
    RegistrationResultBase.__init__(self, series)
    self.volume = None
    self.transform = None

  def save(self, outputDir):
    seriesTypeManager = SeriesTypeManager()
    dictionary = {
      "name": self.name,
      "seriesType": seriesTypeManager.getSeriesType(self.name)
    }
    savedSuccessfully = []
    failedToSave = []
    success, name = self.saveNodeData(self.transform, outputDir, FileExtension.H5, overwrite=True)
    dictionary["transform"] = name + FileExtension.H5
    self.handleSaveNodeDataReturn(success, name, savedSuccessfully, failedToSave)
    success, name = self.saveNodeData(self.volume, outputDir, FileExtension.NRRD, overwrite=True)
    dictionary["volume"] = name + FileExtension.NRRD
    self.handleSaveNodeDataReturn(success, name, savedSuccessfully, failedToSave)
    return dictionary