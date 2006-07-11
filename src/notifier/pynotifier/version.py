#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# version.py
#
# Author: Andreas Büsching <crunchy@bitkipper.net>
#
# version information
#
# $Id: version.py 82 2006-06-14 22:35:47Z crunchy $
#
# Copyright (C) 2004, 2005, 2006 Andreas Büsching <crunchy@bitkipper.net>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.

major_number    = 0
minor_number    = 4
revision_number = 2
extension       = ''

VERSION = "%d.%d.%d%s" % ( major_number, minor_number,
                           revision_number, extension )
