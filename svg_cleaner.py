#!/usr/bin/env python

import re
import xmltodict
import sys
import json
import os
from svg.path import Path, Line, Arc, CubicBezier, QuadraticBezier, parse_path

total_width = 0
total_height = 0
scale_width = 1.0
scale_height = 1.0
max_x = 0
max_y = 0
min_x = 0
min_y = 0

def main():
    filename = sys.argv[1]
    numtaxa = sys.argv[2]
    # potrace -o outputfile -s -k 0.8 -W 10 -H 10 raw_pbm_file
    
    file_name, extension = os.path.splitext(sys.argv[1])
    if extension != '.svg':
        print "can't open this file"
        return
    f = open(filename, 'r')
    xmldict = ''
    xml = f.read()
    xmldict = xmltodict.parse(xml)['svg']
    global total_width, total_height, scale_width, scale_height
    total_width = float(xmldict['@width'].replace('pt',''))
    total_height = float(xmldict['@height'].replace('pt',''))
    xmlpaths = []
    style = {}
    transform = ''
    paths = [] 
    
    # parse original paths
    if 'path' in xmldict:
        xmlpaths = xmldict['path']
    elif 'g' in xmldict:
        xmlpaths = xmldict['g']['path']
        del xmldict['g']['path']
        if '@transform' in xmldict['g']:
            transform = xmldict['g']['@transform']
            if transform != '':
                parse_transform(transform)
    raw_polygons = []
    for path in xmlpaths:
        polygon = path_to_polygon(path['@d'])
        raw_polygons.append(polygon)

    global max_x, max_y, min_x, min_y
    global scale_width, scale_height
    max_x = abs(max_x * scale_width)
    max_y = abs(max_y * scale_height)
    polygons = []
    for polygon in raw_polygons:
        polygon = scale(polygon, scale_width, scale_height)
        polygon = translate(polygon, 0, max_y)
        if threshold_area(bounding_box(polygon), 0.6):
            path = {}
            path['@d'] = nodes_to_path(polygon)
            path['@style'] = "fill:#CCCCCC; stroke:#999999; stroke-width:1"
            paths.append(path) 
            polygons.append(polygon)
        else:
            path = {}
            path['@d'] = nodes_to_path(polygon)
            path['@style'] = "fill:#EEEEEE; stroke:#EEEEEE; stroke-width:1"
            paths.append(path) 

    segments = []   
    radius = max_y / (int(numtaxa)*5)
    polygon_total = []
    for polygon in polygons:
        polygon = cleanup_polygon(polygon, radius)
        polygon = simplify_polygon(polygon)
        polygon = cleanup_polygon(polygon, radius*1.8)
        polygon = simplify_polygon(polygon)
        segments.extend(lineify_path(polygon))
        
        # this path is for the cleaned-up lines
        path = {}
        path['@d'] = nodes_to_path(polygon)
        path['@name'] = "cleaned path"
        path['@style'] = "fill:none; stroke:#FF0000; stroke-width:2"
        paths.append(path) 
    
    # make the raw tree for making nexml:
    (nodes, edges, otus) = make_tree(segments)
    
    # generate nexml:
    nodedict = {}
    otudict = {}
    index = 1
    for otu in otus:
        otudict[str(otu)] = 'otu%d' % index
        index = index+1

    nodes.extend(otus)
    index = 1  
    for node in nodes:
        nodedict[str(node)] = 'node%d' % index
        index = index+1
    
    nexmldict = {}
    nexmldict['nex:nexml'] = {'@xmlns:nex':'http://www.nexml.org/2009'}
    nexmldict['nex:nexml']['@xmlns']="http://www.nexml.org/2009"
    nexmldict['nex:nexml']['@xmlns:rdf']="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    nexmldict['nex:nexml']['@xmlns:xsd']="http://www.w3.org/2001/XMLSchema#"
    nexmldict['nex:nexml']['@xmlns:xsi']="http://www.w3.org/2001/XMLSchema-instance" 
    nexmldict['nex:nexml']['@version'] = '0.9'
    nexmldict['nex:nexml']['otus'] = {'@about':'#otus', '@id':'otus','@label':'taxa'}
    nexmldict['nex:nexml']['otus']['otu'] = []
    for otu in otus:
        nexml_otu = {'@id':otudict[str(otu)]}
        nexml_otu['@about'] = '#%s' % otudict[str(otu)]
        nexml_otu['@label'] = otudict[str(otu)]
        nexmldict['nex:nexml']['otus']['otu'].append(nexml_otu)
    
    nexmldict['nex:nexml']['trees']= {'@about':'#trees1','@id':'trees1','@label':'trees','@otus':'otus'}
#         <tree about="#tree37" id="tree37" label="test_tree" xsi:type="nex:FloatTree">
    currtree = {'@id':'tree1', '@about':'#tree1', '@label':'tree', '@xsi:type':'nex:FloatTree'}
    nexmldict['nex:nexml']['trees']['tree'] = [currtree]
    currtree['node'] = []
    for node in nodes:
        nexml_node = {'@id':nodedict[str(node)]}
        if str(node) in otudict:
            nexml_node['@otu'] = otudict[str(node)]
        currtree['node'].append(nexml_node)   

    nexmldict['nex:nexml']['trees']['edge'] = []
    index = 1
    currtree['edge'] = []
    for edge in edges:
        nexml_edge = {}
        nexml_edge['@id'] = 'edge%d' % index
        nexml_edge['@length'] = str(edge[2]-edge[0])
        nexml_edge['@source'] = nodedict[str([edge[0],edge[1]])]
        nexml_edge['@target'] = nodedict[str([edge[2],edge[3]])]
        currtree['edge'].append(nexml_edge)  
        index = index+1 

    outf = open('test.xml','w')
    outf.write(xmltodict.unparse(nexmldict, pretty=True))
    outf.close()
    
    # generate nexus:
    nexus_str = ""
    nexus_str += "#NEXUS\n"
    nexus_str += "begin TREES;\n"
    nexus_str += "Tree tree=\n"
    nexus_str += tree_to_nexus(otus, nodes, edges)
    nexus_str += ";\nEnd;\n"
    
    outf = open('test.nex','w')
    outf.write(nexus_str)
    outf.close()
                
    # generate svg:
    lines = []
    circles = []
#     circles.extend(nodes_to_circles(nodes))
#     lines.extend(segments_to_lines(edges))
    svgdict = {}
    svgdict['svg'] = {}
    svgdict['svg']['width'] = xmldict['@width']
    svgdict['svg']['height'] = xmldict['@height']
    svgdict['svg']['g'] = [{'path':paths, 'line':lines, 'circle':circles}]

    outf = open('test.svg','w')
    outf.write(xmltodict.unparse(svgdict, pretty=True))
    outf.close()

def tree_to_nexus(otus, nodes, edges):
    otudict = {}
    nodedict = {}
    for i in range(len(otus)):
        nodedict[str(otus[i])] = str('otu%d' % i)
    # find the root: it's the node that is not the y2 of any edge
    root = None
    for node in nodes:
        targetnum = 0
        sourcenum = 0
        if str(node) not in nodedict:
            nodedict[str(node)] = []
        for edge in edges:
            if edge[1] == node[1] and edge[0] == node[0]:
                targetnum += 1
                edgenex = str([edge[2],edge[3]])
                nodedict[str(node)].append(edgenex)
            if edge[3] == node[1] and edge[2] == node[0]:
                sourcenum += 1
        if sourcenum == 0:
            root = node
    return replace_nodes(nodedict, str(root))

def replace_nodes(nodedict, newick):
    # find the nodes in newick:
    nodematcher = re.findall('\[\d+, \d+\]',newick)
    if len(nodematcher) is 0:
        return newick
    else:
        for node in nodematcher:
            # replace the node with the children of the node
            child = str(nodedict[node])
            if '[' in child:
                child = '(' + str(', '.join(nodedict[node])) + ')'
            newick = newick.replace(node, child)                
    return replace_nodes(nodedict, newick)

def scale(polygon, scale_width, scale_height):
    for node in polygon:
        node[0] = int(float(node[0]) * scale_width)
        node[1] = int(float(node[1]) * scale_height)
    return polygon
    
def translate(polygon, x, y):
    for node in polygon:
        node[0] = int(float(node[0]) + x)
        node[1] = int(float(node[1]) + y)
    return polygon

def parse_transform(transform):
    global scale_width, scale_height
    scalematcher = re.search('scale\(([0-9\-\.]+),*(.*?)\)', transform)
    if scalematcher is not None:
        scale_width = float(scalematcher.group(1))
        if scalematcher.group(2) is not None:
            scale_height = float(scalematcher.group(2))
            
def make_tree(segments):
    segments = remove_dups(segments)
    vert_lines = set()
    horiz_lines = set()
    nodes = set()
    levels = set()   
    for seg in segments:
        nodes.add('%03d' % int(seg[1]))
        nodes.add('%03d' % int(seg[3]))
        levels.add('%03d' % int(seg[0]))
        levels.add('%03d' % int(seg[2]))
        seg_str = '%03d %03d %03d %03d' % (int(seg[0]), int(seg[1]), int(seg[2]), int(seg[3]))
        if seg[0] == seg[2]:
            vert_lines.add(seg_str)
        elif seg[1] == seg[3]:
            horiz_lines.add(seg_str)
    
    # how many different levels are there?
    levels = list(levels)
    # sort them backwards because we want to work from the leaves back
    levels.sort(cmp=lambda x,y: cmp(int(y), int(x)))
    # how many different nodes are there?
    nodes = list(nodes)
    nodes.sort(cmp=lambda x,y: cmp(int(x), int(y)))
    
    # for each level, make a node-level out of it by finding the main endpoints of the verticals that go with it.
    node_dict = {}
    sorted_verts = list(vert_lines)
    sorted_verts.sort(cmp=lambda x,y: cmp(x, y))
    for line in sorted_verts:
        coords = re.split(' ',line)
        x = int(coords[0])
        y1 = int(coords[1])
        y2 = int(coords[3])
        if x not in node_dict:
            node_dict[x] = [];
        if y1 == y2:
            continue        
        node_dict[x].append([y1,y2])
    
    node_dict_keys = node_dict.keys()
    node_dict.keys().sort()
    for k in node_dict_keys:
        if len(node_dict[k]) == 0:
            continue
        coalesced_nodes = []
        current_node = node_dict[k][0]
        coalesced_nodes.append(current_node)
        for edge in node_dict[k]:
            e1 = int(current_node[0])
            e2 = int(current_node[1])
            y1 = int(edge[0])
            y2 = int(edge[1])
            # if y1 is in between edge's ends, we're working on this same node
            if y1 <= e2 and y1 >= e1:
                # if y2 is larger than e2, replace e2
                if y2 > e2:
                    current_node = [e1,y2]
                    coalesced_nodes[len(coalesced_nodes)-1] = current_node
            # if y2 is bigger than e2:
            elif y1 > e2:
                # this is a different node, add this to node_dict[x]
                current_node = [y1, y2]
                coalesced_nodes.append(current_node)
        node_dict[k] = coalesced_nodes
    
    # okay, now we know what the nodes are. Match up the edges.
    edges = []
    otus = []
    nodes = set()
    for line in horiz_lines:
        coords = re.split(' ',line)
        x1 = int(coords[0])
        x2 = int(coords[2])
        y1 = int(coords[1])
        y2 = int(coords[3])
        # we want to make the y1 equal to the y1 of the node
        # look for the node that this x1 is in:
        print line
        if x1 in node_dict:
            for node in node_dict[x1]:
                if y1 >= node[0] and y1 <= node[1]:
                    y1 = node[0]
            if len(node_dict[x2]) == 0:
                otus.append([x2, y2])
            else:
                for node in node_dict[x2]:
                    if y2 >= node[0] and y2 <= node[1]:
                        y2 = node[0]
                nodes.add('%d %d' % (x1, y1))
                nodes.add('%d %d' % (x2, y2))
            edges.append([x1, y1, x2, y2])
    final_nodes = []
    for node in nodes:
        coords = re.split(' ',node)
        final_nodes.append([int(coords[0]), int(coords[1])])
    return (final_nodes, edges, otus)

def remove_dups(segments):
    seg_set = set()
    vert_set = set()
    for seg in segments:
        # clean up horizontal lines
        if seg[1] == seg[3]:
            if int(seg[0]) < int(seg[2]):
                seg_set.add('%d %d %d %d' % (seg[0], seg[1], seg[2], seg[3]))
            else:
                seg_set.add('%d %d %d %d' % (seg[2], seg[1], seg[0], seg[3]))
        # clean up vertical lines
        if seg[0] == seg[2]:
            if int(seg[1]) < int(seg[3]):
                seg_set.add('%d %d %d %d' % (seg[0], seg[1], seg[2], seg[3]))
            else:
                seg_set.add('%d %d %d %d' % (seg[0], seg[3], seg[2], seg[1]))
    
    seg_list = []
    for seg in seg_set:
        seg_list.append(re.split(' ',seg))
    for seg in vert_set:
        seg_list.append(re.split(' ',seg))
    return seg_list
    
def segments_to_lines(segments):
    lines = []
    for seg in segments:
        lines.append({'@x1':str(seg[0]), '@y1':str(seg[1]), '@x2':str(seg[2]), '@y2':str(seg[3]), '@stroke-width':'3', '@stroke':'green'})
    return lines

def lineify_path(polygon):
    lines = []
    segment_hash = {}
    last_node = polygon[0]
    for node in polygon:
        lines.append([last_node[0], last_node[1], node[0], node[1]])
        last_node = node
    return lines
       
def cleanup_polygon(polygon, radius):
    # find all the horizontal points
    x_sort_dict = {}
    x_sort_points = [x for x in polygon]
    x_sort_points.sort(cmp=lambda x,y: cmp(float(x[0]), float(y[0])))
    
    curr_x = 0
    for point in x_sort_points:
        if float(point[0]) > (float(curr_x) + float(radius)):
            curr_x = point[0]
        x_sort_dict['%d %d' % (point[0],point[1])] = [curr_x,point[1]]

    new_polygon = []
    for point in polygon:
        new_polygon.append(x_sort_dict['%d %d' % (point[0],point[1])])
        
    # find all the vertical points
    sort_dict = {}
    y_sort_points = [x for x in new_polygon]
    y_sort_points.sort(cmp=lambda x,y: cmp(float(x[1]), float(y[1])))
    curr_y = 0
    for point in y_sort_points:
        if float(point[1]) > (float(curr_y) + float(radius)):
            curr_y = point[1]
        sort_dict['%d %d' % (point[0],point[1])] = [point[0],curr_y]
    polygon = []
    for point in new_polygon:
        polygon.append(sort_dict['%d %d' % (point[0],point[1])])
    return polygon   

# remove all in-between singletons from a cleaned-up polygon
def simplify_polygon(polygon):
    new_polygon = [polygon[0]]
    for i in range(len(polygon)-2):
        add_me = True
        # if the three y-vals are equal
        if (polygon[i][1] == polygon[i+1][1]) and (polygon[i+1][1] == polygon[i+2][1]):
            # if polygon[i+1][0] is between polygon[i][0] and polygon[i+2][0], do not add
            if (polygon[i][0] < polygon[i+1][0] and polygon[i+1][0] < polygon[i+2][0]) or (polygon[i][0] > polygon[i+1][0] and polygon[i+1][0] > polygon[i+2][0]):
                add_me = False
        # if the three x-vals are equal
        if (polygon[i][0] == polygon[i+1][0]) and (polygon[i+1][0] == polygon[i+2][0]):
            # if polygon[i+1][1] is between polygon[i][1] and polygon[i+2][1], do not add
            if (polygon[i][1] < polygon[i+1][1] and polygon[i+1][1] < polygon[i+2][1]) or (polygon[i][1] > polygon[i+1][1] and polygon[i+1][1] > polygon[i+2][1]):
                add_me = False
        if add_me == True:
            new_polygon.append(polygon[i+1])
    return new_polygon

def path_to_polygon(path):
    polygon = []
    global max_x, max_y, min_x, min_y
    new_path = Path()    
    for segment in parse_path(path):
        new_path.append(Line(segment.start, segment.end))
    new_path.closed = True
    nodes = re.findall('[ML]\s*(\d+\.*\d*,\d+\.*\d*)\s*', new_path.d())
    for n in nodes:
        coords = n.split(',')
        if max_x < int(coords[0]):
            max_x = int(coords[0])
        if max_y < int(coords[1]):
            max_y = int(coords[1])
        if min_x > int(coords[0]):
            min_x = int(coords[0])
        if min_y > int(coords[1]):
            min_y = int(coords[1])
        polygon.append([int(coords[0]), int(coords[1])])
    return polygon
    
def nodes_to_path(nodes):
    path_points = []
    for point in nodes:
        path_points.append('%d %d' % (point[0],point[1]))
    return 'M' + 'L'.join(path_points) + 'Z'
          
def nodes_to_circles(nodes):
    circlelist = []
    for i in range(len(nodes)):
        circledict = {}
        coords = nodes[i]
        circledict['@r'] = '3'
        circledict['@stroke'] = 'black'
        circledict['@stroke-width'] = '1'
        circledict['@fill'] = 'yellow'
        circledict['@cx'] = str(coords[0])
        circledict['@cy'] = str(coords[1])
        circlelist.append(circledict)
    return circlelist

def average_color(col):
    matcher = re.match("(..)(..)(..)", col)
    r = matcher.group(1)
    g = matcher.group(2)
    b = matcher.group(3)
    average = (int(r,16) + int(g,16) + int(b,16))/3
    return average

def threshold_area(rect, threshold):
    mins = rect[0]
    maxs = rect[2]
    min_x = float(mins[0])
    min_y = float(mins[1])
    max_x = float(maxs[0])
    max_y = float(maxs[1])
    if abs(float(max_y - min_y) / float(total_height)) > float(threshold):
        return True
    if abs(float(max_x - min_x) / float(total_width)) > float(threshold):
        return True
    return False
    
def bounding_box(polygon):
    x_points = []
    y_points = []
    for point in polygon:
        coord = point
        x_points.append(coord[0])
        y_points.append(coord[1])
    max_x = max(x_points)
    max_y = max(y_points)
    min_x = min(x_points)
    min_y = min(y_points)
    return [[min_x, min_y],[min_x, max_y],[max_x, max_y],[max_x, min_y]]
    
if __name__ == '__main__':
    main()
