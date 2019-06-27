import xml.etree.ElementTree as ET

def _read_name (xml):
    return str(xml.attrib["name"])

def _read_clearance (xml):
    return float(xml.attrib.get('clearance', 0))

def _read_mask (xml):
    masksTag = xml.findall('mask')
    if len(masksTag) > 1:
        raise ValueError ("Handle needs at most one tag mask")
    elif len(masksTag) == 1:
        mask = [ bool(v) for v in masksTag[0].text.split() ]
    else:
        mask = (True, ) * 6
    if len(mask) != 6:
        raise ValueError ("Tag mask must contain 6 booleans")
    return tuple (mask)

def _read_joints (xml):
    jointTags = xml.findall('joint')
    return tuple ( [ jt.attrib["name"] for jt in jointTags ] )

def _read_position (xml):
    positionsTag = xml.findall('position')
    if len(positionsTag) != 1:
        raise ValueError ("Gripper needs exactly one tag position")
    try:
        xyz_wxyz = [ float(x) for x in positionsTag[0].text.split() ]
    except AttributeError:
        xyz_wxyz = []
        pass
    if len(xyz_wxyz) > 0:
        xyz_xyzw = xyz_wxyz[0:3] + xyz_wxyz[4:7] + xyz_wxyz[3:4]
    else:
        attribs = positionsTag[0].attrib
        xyz_xyzw = [ float(x) for x in attribs.get ("xyz", "0 0 0").split() ]
        if int("xyzw" in attribs) + int("wxyz" in attribs) + int("rpy" in attribs) > 1:
            raise ValueError ("Tag position must have only one of rpy, wxyz, xyzw")
        if "xyzw" in attribs:
            xyz_xyzw += [ float(x) for x in attribs["xyzw"].split() ]
        elif "wxyz" in attribs:
            w, x, y, z = [ float(x) for x in attribs["wxyz"].split() ]
            xyz_xyzw += [x, y, z, w]
        elif "rpy" in attribs:
            from math import cos, sin, sqrt
            r, p, y = [ float(x) for x in attribs["rpy"].split() ]
            x = sin(r/2.) * cos(p/2.) * cos(y/2.) - cos(r/2.) * sin(p/2.) * sin(y/2.)
            y = cos(r/2.) * sin(p/2.) * cos(y/2.) + sin(r/2.) * cos(p/2.) * sin(y/2.)
            z = cos(r/2.) * cos(p/2.) * sin(y/2.) - sin(r/2.) * sin(p/2.) * cos(y/2.)
            w = cos(r/2.) * cos(p/2.) * cos(y/2.) + sin(r/2.) * sin(p/2.) * sin(y/2.)
            xyz_xyzw += [x, y, z, w]
    return tuple (xyz_xyzw)

def _read_link (xml):
    linksTag = xml.findall('link')
    if len(linksTag) != 1:
        raise ValueError ("Gripper needs exactly one tag link")
    return str(linksTag[0].attrib['name'])

# Torque constants should not appear in gripper tag.
# There should be one value for each actuated joint.
def _read_torque_constant (xml):
    tcTags = xml.findall('torque_constant')
    if len(tcTags) > 1:
        raise ValueError ("Gripper needs at most one tag torque_constant")
    elif len(tcTags) == 1:
        return float(tcTags[0].attrib['value'])
    else:
        return None

def parse_srdf (srdf, packageName = None, prefix = None):
    """
    parameters:
    - packageName: if provided, the filename is considered relative to this ROS package
    - prefix: if provided, the name of the elements will be prepended with
             prefix + "/"
    """
    import os
    if packageName is not None:
        from rospkg import RosPack
        rospack = RosPack()
        path = rospack.get_path(packageName)
        srdfFn = os.path.join(path, srdf)
    else:
        srdfFn = srdf

    # tree = ET.fromstring (srdfFn)
    tree = ET.parse (srdfFn)
    root = tree.getroot()

    grippers = {}
    for xml in root.iter('gripper'):
        n = _read_name (xml)
        g = { "robot":     prefix,
              "name":      n,
              "clearance": _read_clearance (xml),
              "link":      _read_link (xml),
              "position":  _read_position (xml),
              "joints":    _read_joints (xml),
              }
        tc = _read_torque_constant (xml)
        if tc is not None: g["torque_constant"] = tc
        grippers[ prefix + "/" + n if prefix is not None else n] = g

    handles = {}
    for xml in root.iter('handle'):
        n = _read_name (xml)
        h = { "robot":     prefix,
              "name":      n,
              "clearance": _read_clearance (xml),
              "link":      _read_link (xml),
              "position":  _read_position (xml),
              "mask":      _read_mask (xml),
              }
        handles[ prefix + "/" + n if prefix is not None else n] = h
    return { "grippers": grippers, "handles": handles}
