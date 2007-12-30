from zope.interface import implements
from zope.interface import Interface
from zope.interface import directlyProvides
from zope.interface import providedBy

from zope.component import adapts
from zope.component import getSiteManager
from zope.component import getUtilitiesFor
from zope.component import queryMultiAdapter
from zope.component.interfaces import IComponentRegistry

from Products.GenericSetup.interfaces import IBody
from Products.GenericSetup.interfaces import ISetupEnviron

from Products.GenericSetup.utils import XMLAdapterBase
from Products.GenericSetup.utils import exportObjects
from Products.GenericSetup.utils import importObjects
from Products.GenericSetup.utils import _getDottedName
from Products.GenericSetup.utils import _resolveDottedName

from plone.portlets.interfaces import IPortletType
from plone.portlets.interfaces import IPortletManager

from plone.portlets.constants import USER_CATEGORY, GROUP_CATEGORY, CONTENT_TYPE_CATEGORY

from plone.portlets.manager import PortletManager
from plone.portlets.storage import PortletCategoryMapping
from plone.portlets.registration import PortletType

from Products.CMFPlone.utils import log_deprecated

def dummyGetId():
    return ''

class PortletsXMLAdapter(XMLAdapterBase):
    """In- and exporter for a local portlet configuration
    """
    implements(IBody)
    adapts(IComponentRegistry, ISetupEnviron)
    
    name = 'portlets'
    _LOGGER_ID = 'portlets'
    
    def _exportNode(self):
        # hack around an issue where _getObjectNode expects to have the context
        # a meta_type and a getId method, which isn't the case for a component
        # registry
        if IComponentRegistry.providedBy(self.context):
            self.context.meta_type = 'ComponentRegistry'
            self.context.getId = dummyGetId
        node = self._getObjectNode('portlets')
        if IComponentRegistry.providedBy(self.context):
            del(self.context.meta_type)
            del(self.context.getId)
        node.appendChild(self._extractPortlets())
        self._logger.info('Portlets exported')
        return node

    def _importNode(self, node):
        self._initProvider(node)
        self._logger.info('Portlets imported')

    def _initProvider(self, node):
        if self.environ.shouldPurge():
            self._purgePortlets()
        self._initPortlets(node)

    def _purgePortlets(self):
        registeredPortletTypes = [r.name for r in self.context.registeredUtilities()
                                        if r.provided == IPortletType]
                                    
        for name, portletType in getUtilitiesFor(IPortletType):
            if name in registeredPortletTypes:
                self.context.unregisterUtility(provided=IPortletType, name=name)
        
        portletManagerRegistrations = [r for r in self.context.registeredUtilities()
                                        if r.provided.isOrExtends(IPortletManager)]
        
        for registration in portletManagerRegistrations:
            self.context.unregisterUtility(provided=registration.provided,
                                           name=registration.name)

    def _initPortlets(self, node):
        registeredPortletManagers = [r.name for r in self.context.registeredUtilities()
                                        if r.provided.isOrExtends(IPortletManager)]
        
        for child in node.childNodes:
            if child.nodeName.lower() == 'portletmanager':
                manager = PortletManager()
                name = str(child.getAttribute('name'))
                
                managerType = child.getAttribute('type')
                if managerType:
                    directlyProvides(manager, _resolveDottedName(managerType))
                
                manager[USER_CATEGORY] = PortletCategoryMapping()
                manager[GROUP_CATEGORY] = PortletCategoryMapping()
                manager[CONTENT_TYPE_CATEGORY] = PortletCategoryMapping()
                
                if name not in registeredPortletManagers:
                    self.context.registerUtility(component=manager,
                                                 provided=IPortletManager,
                                                 name=name)
                                                 
            elif child.nodeName.lower() == 'portlet':
                self._initPortletNode(child)
    
    def _extractPortlets(self):
        fragment = self._doc.createDocumentFragment()
        
        registeredPortletTypes = [r.name for r in self.context.registeredUtilities()
                                            if r.provided == IPortletType]
        portletManagerRegistrations = [r for r in self.context.registeredUtilities()
                                            if r.provided.isOrExtends(IPortletManager)]
        
        for r in portletManagerRegistrations:
            child = self._doc.createElement('portletmanager')
            child.setAttribute('name', r.name)

            specificInterface = providedBy(r.component).flattened().next()
            if specificInterface != IPortletManager:
                child.setAttribute('type', _getDottedName(specificInterface))
            
            fragment.appendChild(child)
            
        for name, portletType in getUtilitiesFor(IPortletType):
            if name in registeredPortletTypes:
                fragment.appendChild(self._extractPortletNode(name,
                  portletType))
        
        return fragment
    
    def _extractPortletNode(self, name, portletType):
        child = self._doc.createElement('portlet')
        child.setAttribute('addview', portletType.addview)
        child.setAttribute('title', portletType.title)
        child.setAttribute('description', portletType.description)
            
        for_ = portletType.for_
        #BBB
        for_ = self._BBB_for(for_)
        
        if for_ and for_ != []:
            for i in for_:
                subNode = self._doc.createElement('for')
                subNode.setAttribute('interface', _getDottedName(i))
                child.appendChild(subNode)
        return child
    
    #BBB
    def _BBB_for(self, for_):
        if for_ is None:
            return []
        if type(for_) not in (tuple, list):
            return [for_]
        return for_
        
    def _initPortletNode(self, node):
        registeredPortletTypes = [r.name for r in \
          self.context.registeredUtilities() if r.provided == IPortletType]
        addview = str(node.getAttribute('addview'))
        if addview not in registeredPortletTypes:
            portlet = PortletType()
            portlet.title = str(node.getAttribute('title'))
            portlet.description = str(node.getAttribute('description'))
            portlet.addview = addview
        
            for_ = []
            for subNode in node.childNodes:
                if subNode.nodeName.lower() == 'for':
                    interface_name = str(
                      subNode.getAttribute('interface')
                      )
                    for_.append(interface_name)
            
            interface_name = node.getAttribute('for')
            if interface_name:
                log_deprecated('The "for" attribute of the portlet node in ' \
                 'portlets.xml is deprecated and will be removed in Plone ' \
                 '4.0. Use children nodes of the form <for interface="zope.' \
                 'interface.Interface" /> instead.')
                for_.append(interface_name)

            for_ = [_resolveDottedName(i) for i in for_ if \
                    _resolveDottedName(i) is not None]
            portlet.for_ = for_
            
            self.context.registerUtility(component=portlet,
                                         provided=IPortletType,
                                         name=addview)

def importPortlets(context):
    """Import portlet managers and portlets
    """
    sm = getSiteManager(context.getSite())
    if sm is None or not IComponentRegistry.providedBy(sm):
        logger = context.getLogger('portlets')
        logger.info("Can not register components - no site manager found.")
        return

    # This code was taken from GenericSetup.utils.import.importObjects
    # and slightly simplified. The main difference is the lookup of a named
    # adapter to make it possible to have more than one handler for the same
    # object, which in case of a component registry is crucial.
    importer = queryMultiAdapter((sm, context), IBody, name=u'plone.portlets')
    if importer:
        filename = '%s%s' % (importer.name, importer.suffix)
        body = context.readDataFile(filename)
        if body is not None:
            importer.filename = filename # for error reporting
            importer.body = body

def exportPortlets(context):
    """Export portlet managers and portlets
    """
    sm = getSiteManager(context.getSite())
    if sm is None or not IComponentRegistry.providedBy(sm):
        logger = context.getLogger('portlets')
        logger.info("Nothing to export.")
        return

    # This code was taken from GenericSetup.utils.import.exportObjects
    # and slightly simplified. The main difference is the lookup of a named
    # adapter to make it possible to have more than one handler for the same
    # object, which in case of a component registry is crucial.
    exporter = queryMultiAdapter((sm, context), IBody, name=u'plone.portlets')
    if exporter:
        filename = '%s%s' % (exporter.name, exporter.suffix)
        body = exporter.body
        if body is not None:
            context.writeDataFile(filename, body, exporter.mime_type)
