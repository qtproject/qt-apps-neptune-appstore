import os
import tempfile
import datetime
import shutil
import json

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden, Http404, JsonResponse
from django.contrib import auth
from django.template import Context, loader

from models import App, Category, Vendor
from utilities import parsePackageMetadata, packagePath, iconPath, downloadPath, addSignatureToPackage


def hello(request):
    status = 'ok'

    if settings.APPSTORE_MAINTENANCE:
        status = 'maintenance'
    elif request.REQUEST.get("platform", "") != str(settings.APPSTORE_PLATFORM_ID):
        status = 'incompatible-platform'
    elif request.REQUEST.get("version", "") != str(settings.APPSTORE_PLATFORM_VERSION):
        status = 'incompatible-version'

    return JsonResponse({'status': status})


def login(request):
    status = 'ok'

    try:
        try:
            username = request.REQUEST["username"]
            password = request.REQUEST["password"]
        except KeyError:
            raise Exception('missing-credentials')

        user = auth.authenticate(username = username, password = password)
        if user is None:
            raise Exception('authentication-failed')

        if not user.is_active:
            raise Exception('account-disabled')

        auth.login(request, user)

    except Exception as error:
        status = str(error)

    return JsonResponse({'status': status})


def logout(request):
    status = 'ok'

    if not request.user.is_authenticated():
        status = 'failed'
    logout(request)

    return JsonResponse({'status': status})


def appList(request):
    apps = App.objects.all()
    if 'filter' in request.REQUEST:
        apps = apps.filter(name__contains = request.REQUEST['filter'])
    if 'category_id' in request.REQUEST:
        catId = request.REQUEST['category_id']
        if catId == '0':
            apps = apps.filter(isTopApp__exact = True)
        else:
            apps = apps.filter(category__exact = catId)

    appList = list(apps.values('id', 'name', 'vendor__name', 'rating', 'price', 'briefDescription', 'category'))
    for app in appList:
        app['price'] = float(app['price'])
        app['category_id'] = app['category']
        app['category'] = Category.objects.all().filter(id__exact = app['category_id'])[0].name
        app['vendor'] = app['vendor__name']
        del app['vendor__name']

    # this is not valid JSON, since we are returning a list!
    return JsonResponse(appList, safe = False)


def appDescription(request):
    try:
        app = App.objects.get(id__exact = request.REQUEST['id'])
        return HttpResponse(app.description)
    except:
        raise Http404('no such application: %s' % request.REQUEST['id'])


def appIcon(request):
    try:
        app = App.objects.get(id__exact = request.REQUEST['id'])
        with open(iconPath(app.id), 'rb') as iconPng:
            response = HttpResponse(content_type = 'image/png')
            response.write(iconPng.read())
            return response
    except:
        raise Http404('no such application: %s' % request.REQUEST['id'])


def appPurchase(request):
    if not request.user.is_authenticated():
        return HttpResponseForbidden('no login')

    try:
        deviceId = str(request.REQUEST.get("device_id", ""))
        if settings.APPSTORE_BIND_TO_DEVICE_ID:
            if not deviceId:
                return JsonResponse({'status': 'failed', 'error': 'device_id required'})
        else:
            deviceId = ''

        app = App.objects.get(id__exact = request.REQUEST['id'])
        fromFilePath = packagePath(app.id)

        # we should not use obvious names here, but just hash the string.
        # this would be a nightmare to debug though and this is a development server :)
        toFile = str(app.id) + '_' + str(request.user.id) + '_' + str(deviceId) + '.appkg'
        toPath = downloadPath()
        if not os.path.exists(toPath):
            os.makedirs(toPath)

        if not settings.APPSTORE_NO_SECURITY:
            with open(fromFilePath, 'rb') as package:
                pkgdata = parsePackageMetadata(package)
                addSignatureToPackage(fromFilePath, toPath + toFile, pkgdata['rawDigest'], deviceId)
        else:
            shutil.copyfile(fromFilePath, toPath + toFile)

        return JsonResponse({'status': 'ok',
                             'url': request.build_absolute_uri('/app/download/' + toFile),
                             'expiresIn': int(settings.APPSTORE_DOWNLOAD_EXPIRY) * 60})

        # a cronjob runing "manage.py expiredownloads" every settings.APPSTORE_DOWNLOAD_EXPIRY/2
        # minutes will take care of removing these temporary download files.
    except Exception as error:
        return JsonResponse({ 'status': 'failed', 'error': str(error)})


def appDownload(request, path):
    try:
        response = HttpResponse(content_type = 'application/octetstream')
        with open(downloadPath() + path, 'rb') as pkg:
            response.write(pkg.read())
            response['Content-Length'] = pkg.tell()
        return response
    except:
        raise Http404


def categoryList(request):
    # this is not valid JSON, since we are returning a list!
    return JsonResponse(list(Category.objects.all().order_by('rank').values('id', 'name')), safe = False)


def categoryIcon(request):
    response = HttpResponse(content_type = 'image/png')

    # there are no category icons (yet), so we just return the icon of the first app in this category
    try:
        app = App.objects.filter(category__exact = request.REQUEST['id']).order_by('-dateModified')[0]
        with open(iconPath(app.id), 'rb') as iconPng:
            response.write(iconPng.read())
    except:
        emptyPng = '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x01\x03\x00\x00\x00%\xdbV\xca\x00\x00\x00\x03PLTE\x00\x00\x00\xa7z=\xda\x00\x00\x00\x01tRNS\x00@\xe6\xd8f\x00\x00\x00\nIDAT\x08\xd7c`\x00\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82'
        response.write(emptyPng)

    return response
