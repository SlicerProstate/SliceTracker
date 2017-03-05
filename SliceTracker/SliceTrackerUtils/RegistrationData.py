import logging
import slicer
import os, json
from collections import OrderedDict

from SlicerProstateUtils.constants import FileExtension
from SlicerProstateUtils.mixins import ModuleLogicMixin
from SlicerProstateUtils.decorators import onExceptionReturnNone, logmethod


class RegistrationResults(ModuleLogicMixin):

  # TODO: active result should be in session...
  DEFAULT_JSON_FILE_NAME = "results.json"

  @property
  def activeResult(self):
    return self._getActiveResult()

  @activeResult.setter
  def activeResult(self, series):
    assert series in self._registrationResults.keys()
    self._activeResult = series

  @property
  @onExceptionReturnNone
  def originalTargets(self):
    return self.getMostRecentApprovedCoverProstateRegistration().targets.originalTargets

  @property
  @onExceptionReturnNone
  def intraopLabel(self):
    return self.getMostRecentApprovedCoverProstateRegistration().labels.fixed

  def __init__(self):
    self.resetAndInitializeData()

  def resetAndInitializeData(self):
    self.completed = False
    self.usePreopData = False

    self._activeResult = None
    self.preopVolume = None
    self.preopTargets = None  # TODO: never used???
    self._savedRegistrationResults = []
    self._registrationResults = OrderedDict()
    # TODO: the following should not be here since it is widget depending
    # self.customProgressBar = self.getOrCreateCustomProgressBar()

  def getOrCreateResult(self, series):
    result = self.getResult(series)
    return result if result else self.createResult(series)

  def createResult(self, series):
    assert series not in self._registrationResults.keys()
    self._registrationResults[series] = RegistrationResult(series)
    self.activeResult = series
    return self._registrationResults[series]

  def load(self, filename):
    directory = os.path.dirname(filename)
    self.resetAndInitializeData()
    self.alreadyLoadedFileNames = {}
    with open(filename) as data_file:
      logging.info("reading json file %s" % filename)
      data = json.load(data_file)
      self.completed = data["completed"]
      self.usePreopData = data["usedPreopData"]
      self.zFrameTransform = self._loadOrGetFileData(directory, data["zFrameTransform"], slicer.util.loadTransform)
      # TODO: self.applyZFrameTransform(self.zFrameTransform)

      if data["VOLUME-PREOP-N4"]:
        self.preopVolume = self._loadOrGetFileData(directory, data["VOLUME-PREOP-N4"], slicer.util.loadVolume)
        # self.biasCorrectionDone = True

      self.loadResults(data, directory)
    self._registrationResults = OrderedDict(sorted(self._registrationResults.items()))

  def loadResults(self, data, directory):
    for jsonResult in data["results"]:
      name = jsonResult["name"]
      logging.info("processing %s" % name)
      result = self.createResult(name)

      # TODO: the following should not be here since it is widget depending
      # self.customProgressBar.visible = True
      # self.customProgressBar.maximum = len(data["results"])
      # self.customProgressBar.updateStatus("Loading series registration result %s" % result.name, index+1)
      # slicer.app.processEvents()

      for attribute, value in jsonResult.iteritems():
        logging.info("found %s: %s" % (attribute, value))
        if attribute == 'volumes':
          self._loadResultFileData(value, directory, slicer.util.loadVolume, result.setVolume)
        elif attribute == 'transforms':
          self._loadResultFileData(value, directory, slicer.util.loadTransform, result.setTransform)
        elif attribute == 'targets':
          approved = value.pop('approved', None)
          self._loadResultFileData(value, directory, slicer.util.loadMarkupsFiducialList, result.setTargets)
          if approved:
            targets = self._loadOrGetFileData(directory, approved["fileName"], slicer.util.loadMarkupsFiducialList)
            setattr(result.targets, 'approved', targets)
            approvedRegType = approved[
              "derivedFrom"]  # TODO: derived from is actually already known by approved reg type
            result.targets.modifiedTargets[approvedRegType] = approved["userModified"]
        elif attribute == 'labels':
          self._loadResultFileData(value, directory, slicer.util.loadLabelVolume, result.setLabel)
        elif attribute == 'status':
          result.status.status = value
        else:
          setattr(result, attribute, value)
      if result not in self._savedRegistrationResults:
        self._savedRegistrationResults.append(result)
        # TODO: the following should not be here since it is widget depending
        # self.customProgressBar.text = "Finished loading registration results"

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

  def saveAsJson(self, outputDirectory):
    if not os.path.exists(outputDirectory):
      self.createDirectory(outputDirectory)

    def createResultsList():
      results = []
      for result in sorted(self.getResultsAsList(), key=lambda result: result.seriesNumber):
        results.append(result.toDict())
      return results

    data = {"completed": self.completed,
            "usedPreopData": self.usePreopData,
            # "VOLUME-PREOP-N4": saveBiasCorrectionResult(),
            # "zFrameTransform": saveZFrameTransformation(),
            "results": createResultsList()
            }
    destinationfile = os.path.join(outputDirectory, self.DEFAULT_JSON_FILE_NAME)
    with open(destinationfile, 'w') as outfile:
      logging.info("Writing registration results to %s" % destinationfile)
      json.dump(data, outfile, indent=2)

  def save(self, outputDir):
    savedSuccessfully = []
    failedToSave = []
    # TODO: the following should not be here since it is widget depending
    # self.customProgressBar.visible = True
    for index, result in enumerate(self._registrationResults.values()):
      # TODO: the following should not be here since it is widget depending
      # self.customProgressBar.maximum = len(self._registrationResults)
      # self.customProgressBar.updateStatus("Saving registration result for series %s" % result.name, index + 1)
      slicer.app.processEvents()
      if result not in self._savedRegistrationResults:
        successfulList, failedList = result.save(outputDir)
        savedSuccessfully += successfulList
        failedToSave += failedList
        self._savedRegistrationResults.append(result)
    # TODO: the following should not be here since it is widget depending
    # self.customProgressBar.text = "Registration data successfully saved" if len(failedToSave) == 0 else "Error/s occurred during saving"
    return savedSuccessfully, failedToSave

  def _registrationResultHasStatus(self, series, status):
    if not type(series) is int:
      series = RegistrationResult.getSeriesNumberFromString(series)
    results = self.getResultsBySeriesNumber(series)
    return any(result.status.status == status for result in results) if len(results) else False

  def registrationResultWasApproved(self, series):
    return self._registrationResultHasStatus(series, RegistrationStatus.APPROVED_STATUS)

  def registrationResultWasSkipped(self, series):
    return self._registrationResultHasStatus(series, RegistrationStatus.SKIPPED_STATUS)

  def registrationResultWasRejected(self, series):
    return self._registrationResultHasStatus(series, RegistrationStatus.REJECTED_STATUS)

  def registrationResultWasApprovedOrRejected(self, series):
    return self._registrationResultHasStatus(series, RegistrationStatus.REJECTED_STATUS) or \
           self._registrationResultHasStatus(series, RegistrationStatus.APPROVED_STATUS)

  def getResultsAsList(self):
    return self._registrationResults.values()

  def getMostRecentApprovedCoverProstateRegistration(self):
    mostRecent = None
    for result in self._registrationResults.values():
      if self.getSetting("COVER_PROSTATE", "SliceTracker") in result.name and result.approved:
        mostRecent = result
        break
    return mostRecent

  def getLastApprovedRigidTransformation(self):
    if sum([1 for result in self._registrationResults.values() if result.approved]) == 1:
      lastRigidTfm = None
    else:
      lastRigidTfm = self.getMostRecentApprovedResult().transforms.rigid
    if not lastRigidTfm:
      lastRigidTfm = slicer.vtkMRMLLinearTransformNode()
      slicer.mrmlScene.AddNode(lastRigidTfm)
    return lastRigidTfm

  @onExceptionReturnNone
  def getMostRecentApprovedTransform(self):
    results = sorted(self._registrationResults.values(), key=lambda s: s.seriesNumber)
    for result in reversed(results):
      if result.approved and self.getSetting("COVER_PROSTATE", "SliceTracker") not in result.name:
        return result.getTransform(result.approvedRegistrationType)
    return None

  @onExceptionReturnNone
  def getResult(self, series):
    return self._registrationResults[series]

  def getResultsBySeries(self, series):
    seriesNumber = RegistrationResult.getSeriesNumberFromString(series)
    return self.getResultsBySeriesNumber(seriesNumber)

  def getResultsBySeriesNumber(self, seriesNumber):
    return [result for result in self.getResultsAsList() if seriesNumber == result.seriesNumber]

  def removeResult(self, series):
    try:
      del self._registrationResults[series]
    except KeyError:
      pass

  def exists(self, series):
    return series in self._registrationResults.keys()

  @onExceptionReturnNone
  def _getActiveResult(self):
    return self._registrationResults[self._activeResult]

  @onExceptionReturnNone
  def getMostRecentApprovedResultPriorTo(self, seriesNumber):
    results = sorted(self._registrationResults.values(), key=lambda s: s.seriesNumber)
    results = [result for result in results if result.seriesNumber < seriesNumber]
    for result in reversed(results):
      if result.approved:
        return result
    return None


class RegistrationData(ModuleLogicMixin):

  FILE_EXTENSION = None

  def __init__(self):
    self.initializeMembers()

  def initializeMembers(self):
    self.rigid = None
    self.affine = None
    self.bSpline = None

  def asList(self):
    return [self.rigid, self.affine, self.bSpline]

  def asDict(self):
    return {'rigid': self.rigid, 'affine': self.affine, 'bSpline': self.bSpline}

  @onExceptionReturnNone
  def getFileName(self, node):
    return self.replaceUnwantedCharacters(node.GetName()) + self.FILE_EXTENSION

  def getFileNameByAttributeName(self, name):
    return self.getFileName(getattr(self, name))

  @logmethod(level=logging.INFO)
  def getAllFileNames(self):
    fileNames = {}
    logging.info(self.asDict())
    for regType, node in self.asDict().iteritems():
      fileNames[regType] = self.getFileName(node)
    return fileNames

  def save(self, directory):
    assert self.FILE_EXTENSION is not None
    savedSuccessfully = failedToSave = []
    for node in [node for node in self.asList() if node]:
      success, name = self.saveNodeData(node, directory, self.FILE_EXTENSION)
      self.handleSaveNodeDataReturn(success, name, savedSuccessfully, failedToSave)
    return savedSuccessfully, failedToSave


class Transforms(RegistrationData):

  FILE_EXTENSION = FileExtension.H5

  def __init__(self):
    super(Transforms, self).__init__()


class Targets(RegistrationData):

  FILE_EXTENSION = FileExtension.FCSV

  def __init__(self):
    super(Targets, self).__init__()

  def initializeMembers(self):
    super(Targets, self).initializeMembers()
    self.modifiedTargets = {}
    self.original = None
    self.approved = None

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


class Volumes(RegistrationData):

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


class Labels(RegistrationData):

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


class RegistrationResult(ModuleLogicMixin):

  REGISTRATION_TYPE_NAMES = ['rigid', 'affine', 'bSpline']

  @staticmethod
  def getSeriesNumberFromString(text):
    return int(text.split(": ")[0])

  @property
  @onExceptionReturnNone
  def approvedVolume(self):
    return self.getVolume(self.registrationType)

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
  def targetsWereModified(self):
    return len(self.targets.modifiedTargets) > 0

  @property
  def approved(self):
    return self.status.approved

  @property
  def skipped(self):
    return self.status.skipped

  @property
  def rejected(self):
    return self.status.rejected

  @property
  def cmdFileName(self):
    return str(self.seriesNumber) + "-CMD-PARAMETERS" + self.suffix + FileExtension.TXT

  def __init__(self, series):
    self.name = series

    self.status = RegistrationStatus()

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
    self.status.approve()
    self.targets.approve(registrationType)

  def skip(self):
    self.status.skip()

  def reject(self):
    self.status.reject()

  def printSummary(self):
    logging.debug('# ___________________________  registration output  ________________________________')
    logging.debug(self.__dict__)
    logging.debug('# __________________________________________________________________________________')

  def save(self, outputDir):
    if not os.path.exists(outputDir):
      self.createDirectory(outputDir)

    def saveCMDParameters():
      if self.cmdArguments != "":
        filename = os.path.join(outputDir, self.cmdFileName)
        f = open(filename, 'w+')
        f.write(self.cmdArguments)
        f.close()

    saveCMDParameters()

    savedSuccessfully = []
    failedToSave = []

    # TODO: add lists savedSuccessfully, failedToSave here
    self.transforms.save(outputDir)
    self.targets.save(outputDir)
    self.volumes.save(outputDir)
    self.labels.save(outputDir)
    return savedSuccessfully, failedToSave

  def getApprovedTargetsModifiedStatus(self):
    try:
      modified = self.targets.modifiedTargets[self.registrationType]
    except KeyError:
      modified = [False for i in range(self.targets.approved.GetNumberOfFiducials())]
    return modified

  def toDict(self):
    dictionary = {"name": self.name, "status":self.status.status}
    if self.approved or self.rejected:
      dictionary["targets"] = self.targets.getAllFileNames()
      dictionary["transforms"] = self.transforms.getAllFileNames()
      dictionary["volumes"] = self.volumes.getAllFileNames()
      dictionary["labels"] = self.labels.getAllFileNames()
      dictionary["suffix"] = self.suffix
      if self.approved:
        dictionary["registrationType"] = self.registrationType
    elif self.skipped:
      dictionary["volumes"] = {"fixed": self.volumes.getFileName(self.volumes.fixed)}
    if self.score:
      dictionary["score"] = self.score
    if self.approved:
      dictionary["targets"]["approved"] = {"derivedFrom":self.registrationType,
                                                  "userModified": self.getApprovedTargetsModifiedStatus(),
                                                  "fileName": self.targets.getFileNameByAttributeName("approved")}
    return dictionary


class RegistrationStatus(object):

  UNDEFINED_STATUS = 'undefined'
  SKIPPED_STATUS = 'skipped'
  APPROVED_STATUS = 'approved'
  REJECTED_STATUS = 'rejected'

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
    self.status = self.UNDEFINED_STATUS

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
