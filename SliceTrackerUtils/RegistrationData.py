import logging
import os
from Constants import SliceTrackerConstants, FileExtension
from decorators import onExceptionReturnNone
from mixins import ModuleLogicMixin
from collections import OrderedDict


class RegistrationResults(object):

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
    return self.getMostRecentApprovedCoverProstateRegistration().originalTargets

  @property
  @onExceptionReturnNone
  def intraopLabel(self):
    return self.getMostRecentApprovedCoverProstateRegistration().fixedLabel

  def __init__(self):
    self.resetAndInitializeData()

  def resetAndInitializeData(self):
    self._activeResult = None
    self.preopTargets = None
    self._registrationResults = OrderedDict()

  def save(self, outputDir):
    savedSuccessfully = []
    failedToSave = []

    for result in self._registrationResults.values():
      successfulList, failedList = result.save(outputDir)
      savedSuccessfully += successfulList
      failedToSave += failedList
    return savedSuccessfully, failedToSave

  def _registrationResultHasStatus(self, series, status):
    if not type(series) is int:
      series = RegistrationResult.getSeriesNumberFromString(series)
    results = self.getResultsBySeriesNumber(series)
    return any(result.status == status for result in results) if len(results) else False

  def registrationResultWasApproved(self, series):
    return self._registrationResultHasStatus(series, RegistrationResult.APPROVED_STATUS)

  def registrationResultWasSkipped(self, series):
    return self._registrationResultHasStatus(series, RegistrationResult.SKIPPED_STATUS)

  def registrationResultWasRejected(self, series):
    return self._registrationResultHasStatus(series, RegistrationResult.REJECTED_STATUS)

  def getResultsAsList(self):
    return self._registrationResults.values()

  def getMostRecentApprovedCoverProstateRegistration(self):
    mostRecent = None
    for result in self._registrationResults.values():
      if SliceTrackerConstants.COVER_PROSTATE in result.name and result.approved:
        mostRecent = result
    return mostRecent

  def getLastApprovedRigidTransformation(self):
    nApprovedRegistrations = sum([1 for result in self._registrationResults.values() if result.approved])
    if nApprovedRegistrations == 1:
      lastRigidTfm = None
    else:
      try:
        lastRigidTfm = self.getMostRecentApprovedResult().rigidTransform
      except AttributeError:
        lastRigidTfm = None
    return lastRigidTfm

  def getOrCreateResult(self, series):
    result = self.getResult(series)
    return result if result is not None else self.createResult(series)

  def createResult(self, series):
    assert series not in self._registrationResults.keys()
    self._registrationResults[series] = RegistrationResult(series)
    self.activeResult = series
    return self._registrationResults[series]

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
  def getMostRecentResult(self):
    lastKey = self._registrationResults.keys()[-1]
    return self._registrationResults[lastKey]

  @onExceptionReturnNone
  def getMostRecentApprovedResult(self):
    for result in reversed(self._registrationResults.values()):
      if result.approved:
        return result
    return None

  @onExceptionReturnNone
  def getMostRecentVolumes(self):
    return self.getMostRecentResult().volumes

  @onExceptionReturnNone
  def getMostRecentTransforms(self):
    return self.getMostRecentResult().transforms

  @onExceptionReturnNone
  def getMostRecentTargets(self):
    return self.getMostRecentResult().targets


class RegistrationResult(ModuleLogicMixin):

  REGISTRATION_TYPE_NAMES = ['rigid', 'affine', 'bSpline']

  SKIPPED_STATUS = 'skipped'
  APPROVED_STATUS = 'approved'
  REJECTED_STATUS = 'rejected'
  POSSIBLE_STATES = [SKIPPED_STATUS, APPROVED_STATUS, REJECTED_STATUS]

  @staticmethod
  def getSeriesNumberFromString(text):
    return int(text.split(": ")[0])

  @property
  def volumes(self):
    return {'rigid': self.rigidVolume, 'affine': self.affineVolume, 'bSpline': self.bSplineVolume}

  @property
  def transforms(self):
    return {'rigid': self.rigidTransform, 'affine': self.affineTransform, 'bSpline': self.bSplineTransform}

  @property
  def targets(self):
    return {'rigid': self.rigidTargets, 'affine': self.affineTargets, 'bSpline': self.bSplineTargets}

  @property
  @onExceptionReturnNone
  def approvedTargets(self):
    return self.targets[self.approvedRegistrationType]

  @property
  @onExceptionReturnNone
  def approvedVolume(self):
    return self.volumes[self.approvedRegistrationType]

  @property
  def approved(self):
    return self.status == self.APPROVED_STATUS

  @property
  def skipped(self):
    return self.status == self.SKIPPED_STATUS

  @property
  def rejected(self):
    return self.status == self.REJECTED_STATUS

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
    return len(self.modifiedTargets) > 0

  def __init__(self, series):
    self.name = series

    self.status = None
    self.approvedRegistrationType = None

    self._initVolumes()
    self._initTransforms()
    self._initTargets()
    self._initLabels()

    self.cmdArguments = ""
    self.suffix = ""
    self.score = None

    self.modifiedTargets = {}

  def isGoingToBeMoved(self, targetList, index):
    assert targetList in self.targets.values()
    if not self.modifiedTargets.has_key(targetList):
      self.modifiedTargets[targetList] = {}
    if not self.modifiedTargets[targetList].has_key(index):
      originalPosition = [0.0, 0.0, 0.0]
      targetList.GetNthFiducialPosition(index, originalPosition)
      self.modifiedTargets[targetList][index] = originalPosition

  def _initLabels(self):
    self.movingLabel = None
    self.fixedLabel = None

  def _initTargets(self):
    self.rigidTargets = None
    self.affineTargets = None
    self.bSplineTargets = None
    self.originalTargets = None

  def _initTransforms(self):
    self.rigidTransform = None
    self.affineTransform = None
    self.bSplineTransform = None

  def _initVolumes(self):
    self.fixedVolume = None
    self.movingVolume = None
    self.rigidVolume = None
    self.affineVolume = None
    self.bSplineVolume = None

  def _getAllFileNames(self, keyFunction):
    fileNames = {}
    for regType in self.REGISTRATION_TYPE_NAMES:
      fileNames[regType] = keyFunction(regType)
    return fileNames

  def _getFileName(self, node, extension):
    if node:
      return ModuleLogicMixin.replaceUnwantedCharacters(node.GetName()) + extension
    return None

  def setVolume(self, regType, volume):
    self._setRegAttribute(regType, "Volume", volume)

  def getVolume(self, regType):
    return self._getRegAttribute(regType, "Volume")

  def setTransform(self, regType, transform):
    self._setRegAttribute(regType, "Transform", transform)

  def getTransform(self, regType):
    return self._getRegAttribute(regType, "Transform")

  def setTargets(self, regType, targets):
    self._setRegAttribute(regType, "Targets", targets)

  def getTargets(self, regType):
    return self._getRegAttribute(regType, "Targets")

  def _setRegAttribute(self, regType, attributeType, value):
    assert regType in self.REGISTRATION_TYPE_NAMES
    setattr(self, regType+attributeType, value)

  def _getRegAttribute(self, regType, attributeType):
    assert regType in self.REGISTRATION_TYPE_NAMES
    return getattr(self, regType+attributeType)

  def approve(self, registrationType):
    assert registrationType in self.REGISTRATION_TYPE_NAMES
    self.approvedRegistrationType = registrationType
    self.status = self.APPROVED_STATUS

  def skip(self):
    self.status = self.SKIPPED_STATUS

  def reject(self):
    self.status = self.REJECTED_STATUS

  def printSummary(self):
    logging.debug('# ___________________________  registration output  ________________________________')
    logging.debug(self.__dict__)
    logging.debug('# __________________________________________________________________________________')

  def save(self, outputDir):
    if not os.path.exists(outputDir):
      self.createDirectory(outputDir)

    savedSuccessfully = []
    failedToSave = []

    def saveCMDParameters():
      if self.cmdArguments != "":
        filename = os.path.join(outputDir, self.cmdFileName)
        f = open(filename, 'w+')
        f.write(self.cmdArguments)
        f.close()

    def saveTransformations():
      for transformNode in [node for node in self.transforms.values() if node]:
        success, name = self.saveNodeData(transformNode, outputDir, FileExtension.H5)
        self.handleSaveNodeDataReturn(success, name, savedSuccessfully, failedToSave)

    def saveTargets():
      for targetNode in [node for node in self.targets.values() if node]:
        success, name = self.saveNodeData(targetNode, outputDir, FileExtension.FCSV)
        self.handleSaveNodeDataReturn(success, name, savedSuccessfully, failedToSave)

    def saveApprovedTargets():
      if self.approved:
        fileName = self.approvedTargets.GetName().replace("-TARGETS-", "-APPROVED-TARGETS-")
        success, name = self.saveNodeData(self.approvedTargets, outputDir, FileExtension.FCSV, name=fileName)
        self.handleSaveNodeDataReturn(success, name, savedSuccessfully, failedToSave)

    def saveVolumes():
      for volumeNode in [node for node in self.volumes.values() if node]:
        success, name = self.saveNodeData(volumeNode, outputDir, FileExtension.NRRD)
        self.handleSaveNodeDataReturn(success, name, savedSuccessfully, failedToSave)

    def saveLabels():
      for labelVolume in [self.fixedLabel, self.movingLabel]:
        if labelVolume:
          success, name = self.saveNodeData(labelVolume, outputDir, FileExtension.NRRD)
          self.handleSaveNodeDataReturn(success, name, savedSuccessfully, failedToSave)

    saveCMDParameters()
    saveTransformations()
    saveTargets()
    saveApprovedTargets()
    saveVolumes()
    saveLabels()

    return savedSuccessfully, failedToSave

  @property
  def cmdFileName(self):
    return str(self.seriesNumber) + "-CMD-PARAMETERS" + self.suffix + FileExtension.TXT

  def getTransformFileName(self, regType):
    return self._getFileName(self.getTransform(regType), FileExtension.H5)

  def getVolumeFileName(self, regType):
    return self._getFileName(self.getVolume(regType), FileExtension.NRRD)

  def getTargetFileName(self, regType):
    return self._getFileName(self.getTargets(regType), FileExtension.FCSV)

  def getAllTargetFileNames(self):
    return self._getAllFileNames(self.getTargetFileName)

  def getAllTransformationFileNames(self):
    return self._getAllFileNames(self.getTransformFileName)

  def getAllVolumeFileNames(self):
    return self._getAllFileNames(self.getVolumeFileName)

  def getLabelFileName(self, attributeName):
    label = getattr(self, attributeName)
    if not label:
      return None
    return self._getFileName(label, FileExtension.NRRD)

  def toDict(self):
    #TODO: targetsWereModified
    return {self.name:{"targets":self.getAllTargetFileNames(), "transforms":self.getAllTransformationFileNames(),
                       "volumes":self.getAllVolumeFileNames(), "approvedRegistrationType":self.approvedRegistrationType,
                       "suffix":self.suffix, "status":self.status, "score": self.score,
                       "fixedLabel":self.getLabelFileName("fixedLabel"),
                       "movingLabel":self.getLabelFileName("movingLabel")}}