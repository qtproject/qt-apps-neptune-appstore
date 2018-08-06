#############################################################################
##
## Copyright (C) 2016 Pelagicore AG
## Contact: https://www.qt.io/licensing/
##
## This file is part of the Neptune Deployment Server
##
## $QT_BEGIN_LICENSE:GPL-QTAS$
## Commercial License Usage
## Licensees holding valid commercial Qt Automotive Suite licenses may use
## this file in accordance with the commercial license agreement provided
## with the Software or, alternatively, in accordance with the terms
## contained in a written agreement between you and The Qt Company.  For
## licensing terms and conditions see https://www.qt.io/terms-conditions.
## For further information use the contact form at https://www.qt.io/contact-us.
##
## GNU General Public License Usage
## Alternatively, this file may be used under the terms of the GNU
## General Public License version 3 or (at your option) any later version
## approved by the KDE Free Qt Foundation. The licenses are as published by
## the Free Software Foundation and appearing in the file LICENSE.GPL3
## included in the packaging of this file. Please review the following
## information to ensure the GNU General Public License requirements will
## be met: https://www.gnu.org/licenses/gpl-3.0.html.
##
## $QT_END_LICENSE$
##
## SPDX-License-Identifier: GPL-3.0
##
#############################################################################

import os

from django import forms
from django.conf import settings
from django.conf.urls import patterns
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, get_object_or_404
from django.utils.translation import ugettext as _
from django.utils.translation import ugettext_lazy

from store.models import *
from utilities import parseAndValidatePackageMetadata, writeTempIcon, makeTagList

class CategoryAdminForm(forms.ModelForm):
    class Meta:
        exclude = ["id", "rank"]

    def save(self, commit=False):
        m = super(CategoryAdminForm, self).save(commit)
        try:
            test = Category.objects.all().order_by('-rank')[:1].values('rank')[0]['rank'] + 1
        except:
            test = 0
        m.rank = test
        return m

class CategoryAdmin(admin.ModelAdmin):
    form = CategoryAdminForm
    list_display = ('name', 'move')
    ordering = ('rank',)

    def save_model(self, request, obj, form, change):
        obj.save()

    def name(self, obj):
        # just to forbid sorting by name
        return obj.name
    name.short_description = ugettext_lazy('Item caption')

    def move(self, obj):
        """
        Returns html with links to move_up and move_down views.
        """
        button = u'<a href="%s"><img src="%simg/admin/arrow-%s.gif" /> %s</a>'
        prefix = settings.STATIC_URL

        link = '%d/move_up/' % obj.pk
        html = button % (link, prefix, 'up', _('up')) + " | "
        link = '%d/move_down/' % obj.pk
        html += button % (link, prefix, 'down', _('down'))
        return html
    move.allow_tags = True
    move.short_description = ugettext_lazy('Move')

    def get_urls(self):
        admin_view = self.admin_site.admin_view
        urls = patterns('',
            (r'^(?P<item_pk>\d+)/move_up/$', admin_view(self.move_up)),
            (r'^(?P<item_pk>\d+)/move_down/$', admin_view(self.move_down)),
        )
        return urls + super(CategoryAdmin, self).get_urls()

    def move_up(self, request, item_pk):
        """
        Decrease rank (change ordering) of the menu item with
        id=``item_pk``.
        """
        if self.has_change_permission(request):
            item = get_object_or_404(Category, pk=item_pk)
            item.decrease_rank()
        else:
            raise PermissionDenied
        return redirect('admin:store_category_changelist')

    def move_down(self, request, item_pk):
        """
        Increase rank (change ordering) of the menu item with
        id=``item_pk``.
        """
        if self.has_change_permission(request):
            item = get_object_or_404(Category, pk=item_pk)
            item.increase_rank()
        else:
            raise PermissionDenied
        return redirect('admin:store_category_changelist')



class AppAdminForm(forms.ModelForm):
    class Meta:
        exclude = ["appid", "name", "tags", "architecture", 'version']

    appId = ""
    name = ""

    def clean(self):
        cleaned_data = super(AppAdminForm, self).clean()
        file = cleaned_data.get('file')

        # validate package
        pkgdata = None
        try:
            pkgdata = parseAndValidatePackageMetadata(file)
        except Exception as error:
            raise forms.ValidationError(_('Validation error: %s' % str(error)))

        self.appId = pkgdata['info']['id']
        self.name = pkgdata['storeName']
        self.architecture = pkgdata['architecture']

        # check if this really is an update
        if hasattr(self, 'instance') and self.instance.appid:
            if self.appId != self.instance.appid:
                raise forms.ValidationError(_('Validation error: an update cannot change the application id, tried to change from %s to %s' % (self.instance.appid, self.appId)))
            elif self.architecture != self.instance.architecture:
                raise forms.ValidationError(_('Validation error: an update cannot change the application architecture from %s to %s' % (self.instance.architecture, self.architecture)))
        else:
            try:
                if App.objects.get(appid__exact = self.appId, architecture__exact = self.architecture):
                    raise forms.ValidationError(_('Validation error: another application with id %s and architecture %s already exists' % (str(self.appId), str(self.architecture))))
            except App.DoesNotExist:
                pass

        # write icon into file to serve statically
        success, error = writeTempIcon(self.appId, self.architecture, pkgdata['icon'])
        if not success:
            raise forms.ValidationError(_(error))

        return cleaned_data

    def save(self, commit=False):
        m = super(AppAdminForm, self).save(commit)
        m.appid = self.appId
        m.name = self.name
        m.architecture = self.architecture

        m.file.seek(0)
        pkgdata = parseAndValidatePackageMetadata(m.file)
        m.tags = makeTagList(pkgdata)
        return m


class AppAdmin(admin.ModelAdmin):
    form = AppAdminForm
    list_display = ('name', 'appid', 'architecture', 'version')

    def save_model(self, request, obj, form, change):
        obj.save()


admin.site.register(Category, CategoryAdmin)
admin.site.register(Vendor)
admin.site.register(App, AppAdmin)
