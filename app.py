import os
import sys
from PIL import Image
import simplejson
import traceback
from flask import Flask, request, render_template, redirect, session, url_for, send_from_directory, jsonify, flash, Response, make_response
import pymongo
from flask_bootstrap import Bootstrap
from subprocess import check_output, call
from werkzeug.utils import secure_filename
from lib.upload_file import uploadfile
import glob
import re
import pprint
import json
from subprocess import Popen, PIPE, STDOUT
from astroid import parse
from Parser import parseCode
from datetime import datetime
from bson import ObjectId
import pdfkit
import bcrypt
import difflib

#Object for Metrics class
from metrics import Metrics_defined
metrics_obj = Metrics_defined()

app = Flask(__name__)

# MONGO
myclient = pymongo.MongoClient("mongodb://localhost:27017/")
# DB Configuration
mydb = myclient["sdqa"]
Code = mydb["source_code"]
User = mydb["user_profiling"]


# Upload file Configuration
app.config['UPLOAD_FOLDER'] = 'data/'
app.config['THUMBNAIL_FOLDER'] = 'data/thumbnail/'
app.config['THUMBNAIL_FOLDER2'] = 'data/thumbnail/temp'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = set(['py'])
IGNORED_FILES = set(['.gitignore'])

bootstrap = Bootstrap(app)

class getFile:
    def get_fileName(self):
        files = [f for f in os.listdir(app.config['UPLOAD_FOLDER']) if os.path.isfile(
            os.path.join(app.config['UPLOAD_FOLDER'], f)) and f not in IGNORED_FILES]
        return files

    def get_classes(self):
        lis = obj.get_fileName()
        item = 0
        array = []
        for item in lis:
            f = open("data/"+item, "r")
            ast = parse(f.read())
            test = parseCode()
            for temp in test.find_classes(ast):
                array.append(temp)
        return array

    def get_full_classname(self,files):
        
        with open("data/"+ files, "r") as file:

            imports = []
            classes = []

            for line in file:
                if 'import' in line:
                    for x in line.split('import')[1].split(','):
                        imports.append(x.strip())

                if 'class ' in line:
                    classes.append(line.split('class')[1][1:-2].strip())

        return classes


obj = getFile()


def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def gen_file_name(filename):
    """
    If file was exist already, rename it and return a new name
    """

    i = 1
    while os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], filename)):
        name, extension = os.path.splitext(filename)
        filename = '%s_%s%s' % (name, str(i), extension)
        i += 1

    return filename


def create_thumbnail(image):
    try:
        base_width = 80
        img = Image.open(os.path.join(app.config['THUMBNAIL_FOLDER'], image))
        w_percent = (base_width / float(img.size[0]))
        h_size = int((float(img.size[1]) * float(w_percent)))
        img = img.resize((base_width, h_size), PIL.Image.ANTIALIAS)
        img.save(os.path.join(app.config['THUMBNAIL_FOLDER2'], image))

        return True

    except:
        # print traceback.format_exc()
        return False


@app.route('/login', methods=['POST', 'GET'])
def login():
    
    if request.method == 'POST':
        login_user = User.find_one({'name' : request.form['username']})

        if login_user:
            
            if bcrypt.checkpw(request.form['pass'].encode('utf-8'), login_user['password'].encode('utf-8')):

                session['username'] = request.form['username']
                return redirect(url_for('index'))

    # return 'Invalid username/password combination'
    return render_template('login.html')

@app.route('/register', methods=['POST', 'GET'])
def register():
    if request.method == 'POST':
        
        existing_user = User.find_one({'name' : request.form['username']})

        if existing_user is None:
            hashpass = bcrypt.hashpw(request.form['pass'].encode('utf-8'), bcrypt.gensalt())
            User.insert({'name' : request.form['username'], 'password' : hashpass.decode('utf-8')})
            session['username'] = request.form['username']
            flash("Account created!", 'primary')
            return redirect(url_for('index'))
        
        flash('That username already exists!', 'warning')

    return render_template('register.html')


@app.route('/logout', methods=['POST', 'GET'])
def logout():

    session.pop('username', None)
    return redirect(url_for('index'))



def get_logged_id():
    temp = User.find_one({"name" : session['username']})
    id = temp.get('_id')
    return id



@app.route("/upload", methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        files = request.files['file']

        if files:
            filename = secure_filename(files.filename)
            filename = gen_file_name(filename)
            mime_type = files.content_type

            if not allowed_file(files.filename):
                result = uploadfile(
                    name=filename, type=mime_type, size=0, not_allowed_msg="File type not allowed")

            else:
                # save file to db
                uploaded_file_path = os.path.join(
                    app.config['UPLOAD_FOLDER'], filename)
                files.save(uploaded_file_path)

                data = {
                    'User_id' : get_logged_id(),
                    'Source_code_filename': filename,
                    'Report_name': "Temp",
                    'Date_name': datetime.today()
                }
                Code.insert_one(data)
                # print(insertData.inserted_id)
                flash('Python File Uploaded Successfully', 'success')

                # create thumbnail after saving
                if mime_type.startswith('text/plain'):
                    create_thumbnail('py-logo.png')

                # get file size after saving
                size = os.path.getsize(uploaded_file_path)

                # return json for js call back
                result = uploadfile(name=filename, type=mime_type, size=size)

            return simplejson.dumps({"files": [result.get_file()]})

    if request.method == 'GET':
        # get all files for logged in user
        get_ids = Code.find({'User_id' : get_logged_id()})
        files = []
        for x in get_ids:
            files.append(x['Source_code_filename'])

        file_display = []

        for f in files:
            size = os.path.getsize(os.path.join(
                app.config['UPLOAD_FOLDER'], f))
            file_saved = uploadfile(name=f, size=size)
            file_display.append(file_saved.get_file())

        return simplejson.dumps({"files": file_display})

    return redirect(url_for('index'))


@app.route("/delete/<string:filename>", methods=['DELETE'])
def delete(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file_thumb_path = os.path.join(app.config['THUMBNAIL_FOLDER'], filename)

    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            # Deleting data from database
            get_filename = Code.find({'Source_code_filename' : filename})
            for x in get_filename:
                Code.delete_many({'Source_code_filename' : x['Source_code_filename']})

            if os.path.exists(file_thumb_path):
                os.remove(file_thumb_path)
            
            return simplejson.dumps({filename: 'True'})

        except:
            return simplejson.dumps({filename: 'False'})


# serve static files
@app.route("/thumbnail/<string:filename>", methods=['GET'])
def get_thumbnail(filename):
    return send_from_directory(app.config['THUMBNAIL_FOLDER'], filename=filename)


@app.route("/data/<string:filename>", methods=['GET'])
def get_file(filename):

    return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER']), filename= filename)

def get_contents(filename):
    file_path = os.path.join(filename)
    content = ''
    with open(file_path, 'r') as file:
        content = file.read()
        content = content.split('\n')
        return content

def make_diff(old, new):
    """
    Render in HTML the diff between two texts
    """
    df = difflib.HtmlDiff()
    old_lines = old.splitlines(1)
    new_lines = new.splitlines(1)
    html = df.make_table(old_lines, new_lines, context=True)
    html = html.replace(' nowrap="nowrap"','')
    return html

def files_comparison(fromfile, tofile):
        try:
            fromlines = open(fromfile, 'U').readlines()
            tolines = open(tofile, 'U').readlines()
            diff = difflib.HtmlDiff().make_file(fromlines,tolines,fromfile,tofile)
            # path = os.path.basename(fromfile) + '_' + os.path.basename(tofile) + '_diff.html'
            path = "Comparison Report.html"
            f = open(path,'w')
            f.write(diff)
            f.close()
            import webbrowser
            webbrowser.open_new_tab(path)
            return path
        except Exception as e:
            # self.logger.error("failed to diff files %s, %s: %s", fromfile, tofile, str(e))
            return None 
   
@app.route('/trend_analysis', methods=['GET', 'POST'])
def trend_analysis():

    obj = getFile()
    lis = obj.get_fileName()
    filename = ''

    if request.method == 'POST':
        previous = request.form.get('file2')
        evolved_file = request.files['file']

        if evolved_file:
            filename = secure_filename(evolved_file.filename)
            filename = gen_file_name(filename)
            mime_type = evolved_file.content_type

            if not allowed_file(evolved_file.filename):
                result = uploadfile(
                    name=filename, type=mime_type, size=0, not_allowed_msg="File type not allowed")

            else:
                # save file to db
                uploaded_file_path = os.path.join(
                    app.config['UPLOAD_FOLDER'], filename)
                evolved_file.save(uploaded_file_path)

                data = {
                    'User_id' : get_logged_id(),
                    'Source_code_filename': filename,
                    'Report_name': "Temp",
                    'Date_name': datetime.today()
                }
                Code.insert_one(data)
                # print(insertData.inserted_id)
                flash('New Version Upload Successfully!', 'success')

                # create thumbnail after saving
                if mime_type.startswith('text/plain'):
                    create_thumbnail('py-logo.png')

                # get file size after saving
                size = os.path.getsize(uploaded_file_path)

                # return json for js call back
                result = uploadfile(name=filename, type=mime_type, size=size)

            # return simplejson.dumps({"files": [result.get_file()]})
        
        previous_version = 'data/' + previous
        new_version = 'data/'+ filename

        with open(previous_version, 'r') as file1:
            with open(new_version, 'r') as file2:
                same = set(file2).symmetric_difference(file1)

        same.discard('\n')
        array = []
        for line in same:
            array.append(line)

        files_comparison(previous_version, new_version)
        flash('Comparison Report Generated Successfully!!', 'success')

        previous_content = get_contents(previous_version)
        new_content = get_contents(new_version)

        from Design_Smells_Specific_file import DesignSmells_2
        obj = DesignSmells_2()
        #1
        lpl = obj.detect_LPL(filename)
        #2
        lm = obj.detect_LM(filename)
        #3
        lbcl = obj.detect_LBCL(filename)
        #4
        lc = obj.large_class(filename)
        #5 remaining
        sak = obj.swiss_army_knife(filename)
        #6
        data_class = obj.data_class(filename)
        
        new_smells = len(lpl) + len(lm) + len(lbcl) + len(lc) + len(sak) + len(data_class)

        #1
        lpl = obj.detect_LPL(previous)
        #2
        lm = obj.detect_LM(previous)
        #3
        lbcl = obj.detect_LBCL(previous)
        #4
        lc = obj.large_class(previous)
        #5 remaining
        sak = obj.swiss_army_knife(previous)
        #6
        data_class = obj.data_class(previous)
        
        previous_smells = len(lpl) + len(lm) + len(lbcl) + len(lc) + len(sak) + len(data_class)

        from Design_Smells import DesignSmells
        obj = DesignSmells()

        #1
        lpl = obj.detect_LPL()
        #2
        lm = obj.detect_LM()
        #3
        lbcl = obj.detect_LBCL()
        #4
        lc = obj.large_class()
        lc_len = len(lc)
        #5 remaining
        sak = obj.swiss_army_knife()
        #6
        data_class = obj.data_class()

        files_smells = get_individual_files_smells(lpl,lm,lbcl,lc,sak,data_class)
    
        return render_template('trend_analysis.html', array = array, lis = lis, previous_content = previous_content, new_content = new_content,
        files_smells=files_smells, new_smells = new_smells, previous_smells = previous_smells, previous=previous, filename = filename)
    else:
        return render_template('trend_analysis.html', lis = lis)
    
    

@app.route('/', methods=['GET', 'POST'])
def index():
    if 'username' in session:
        return render_template('index.html')

    return render_template('login.html')



@app.route('/uploadFile', methods=['GET', 'POST'])
def uploadFile():
    return render_template('upload.html')


@app.route('/metrics', methods=['GET', 'POST'])
def metrics():
    
    if request.method == 'POST':
        selected_option = request.form['options']
        lis = obj.get_fileName()
        item = 0
        if selected_option == "LCOM":
            temp = []
            for item in lis:
                temp.append(metrics_obj.lcom4(item))

                return render_template("metrics.html", lcom=metrics_obj.lcom4(item), threshold=compare_LCOM(item), filename=item, selected_option=selected_option)
        elif selected_option == "Number of Methods":
            dict = {}
            array_nom = []
            t = []
            for item in lis:
                array_nom.append(metrics_obj.Number_of_methods(item))
                dict[item] = metrics_obj.Number_of_methods(item)
                t.append(compare_NOM(item))
            labels = lis
            values = array_nom
            return render_template("metrics.html", dict=dict, threshold=t, selected_option=selected_option, title='NOM Metric Threshold', max=80, labels=labels, values=values)

        elif selected_option == "Number of Public Methods":
            dict = {}
            array_nom = []
            t = []
            for item in lis:
                array_nom.append(metrics_obj.Number_of_public_methods(item))
                dict[item] = metrics_obj.Number_of_public_methods(item)
                t.append(compare_NOM(item))
            labels = lis
            values = array_nom
            return render_template("metrics.html", dict=dict, threshold=t, selected_option=selected_option, title='NOPM Metric Threshold', max=600, labels=labels, values=values)

        elif selected_option == "Number of Parameters":
            dict = {}
            array_nom = []
            cn = []
            cn2 = []
            for item in lis:
                array_nom.append(metrics_obj.Number_of_parameters(item))
                dict[item] = metrics_obj.Number_of_parameters(item)
                cn.append(compare_NOP(item))
            for x in cn:
                for y in x:
                    cn2.append(y)
            labels = lis
            values = array_nom
            return render_template("metrics.html", parameters=dict, threshold=cn2, selected_option=selected_option, title='NOP Metric Threshold', max=30, labels=labels, values=values)

        elif selected_option == "Number of Fields":

            dict = {}
            array_nof = []
            t = []
            for item in lis:
                array_nof.append(metrics_obj.Number_of_fields(item))
            for item in lis:
                dict[item] = metrics_obj.Number_of_fields(item)
                t.append(compare_NOF(item))
            labels = lis
            values = array_nof
            return render_template("metrics.html", dict=dict, threshold=t, selected_option=selected_option, title='NOF Metric Threshold', max=30, labels=labels, values=values)

        elif selected_option == "LOC":
            data = {'Task': 'Hours per Day', 'Classes lies within Normal Threshold': 1,
                    'Quit Above Threshold': 0, 'Dangerously Above threshold': 0}
            array_loc_val = []
            dict = {}
            for item in lis:
                array_loc_val.append(metrics_obj.get_LOC(item))
                dict[item] = metrics_obj.LOC_metrics(item)

            labels = lis
            values = array_loc_val

            return render_template("metrics.html", loc=dict, selected_option=selected_option, data=data, title='LOC Metric Threshold', max=300, labels=labels, values=values)

        elif selected_option == "Cyclomatic Complexity":

            dict = {}
            array_val = []
            for item in lis:
                array_val.append(metrics_obj.cyclomatic_complexity(item))
                dict[item] = metrics_obj.cyclomatic_complexity(item)
            labels = lis
            values = array_val
            return render_template("metrics.html", cc_value2=dict, threshold=compare_CC(item), selected_option=selected_option, title='CC Metric Threshold', max=10, labels=labels, values=values)

        elif selected_option == "WMC":
            for item in lis:
                return render_template("metrics.html", filename=item,  wmc= metrics_obj.get_WMC(item), threshold=compare_WMC(item), selected_option=selected_option)
        
        elif selected_option == "Number of Accessors":
            for item in lis:
                dict = {}
                dict[item] = metrics_obj.Number_of_accessors(item)
                return render_template("metrics.html", filename=item,  NOA = dict, threshold = compare_NOA(item), selected_option=selected_option)

        elif selected_option == "Methods-LOC":
            for item in lis:
                return render_template("metrics.html", filename=item, threshold = compare_NOM_LOC(item), NOML = metrics_obj.get_NOML(item), selected_option=selected_option)

        elif selected_option == "Number of Superclasses":
            for item in lis:
                dit = {}
                dict = {}
                for class_ in getFile().get_full_classname(item):
                    dict[class_] = metrics_obj.dit_list(class_ , item)
                    dit[item] = dict
                return render_template("metrics.html", filename=item, threshold = compare_NOM_LOC(item), SUP = dit, selected_option=selected_option)

        else:
            return render_template("metrics.html", selected_option=selected_option)

    else:
        # print(metrics_obj.testing("phones.py"))
        return render_template("metrics.html")

@app.route('/Design_smells')
def google_pie_chart():

    from Design_Smells import DesignSmells
    obj = DesignSmells()

    #1
    lpl = obj.detect_LPL()
    #2
    lm = obj.detect_LM()
    #3
    lbcl = obj.detect_LBCL()
    #4
    lc = obj.large_class()
    lc_len = len(lc)
    #5 remaining
    sak = obj.swiss_army_knife()
    #6
    data_class = obj.data_class()

    total = len(lpl) + len(lm) + len(lbcl) + lc_len + len(sak) + len(data_class)
    data = {'Task': 'Hours per Day', 'Long Parameter List': len(lpl), 'Long Method(LM)': len(lm), 
    'Long Base Class List(LBCL)': len(lbcl), 'Large Class(LC)': lc_len,
    'Swiss Army Knife' : len(sak), 'Data Class' : len(data_class)}

    files_smells = get_individual_files_smells(lpl,lm,lbcl,lc,sak,data_class)

    return render_template('design_smells.html', data=data, lpl=lpl, lm = lm, lbcl = lbcl, lc=lc, data_class=data_class, sak=sak, 
    total = total, files_smells = files_smells)

def get_individual_files_smells(lpl,lm,lbcl,lc,sak,data_class):

    obj = getFile()
    lis = obj.get_fileName()
    dict2 = {}
    su = {}
    temp = []
    new_dict = {}
    counter = 0

    for keys, values in lpl.items():
        gen = (x for x in lis if x == keys)
        for x in gen:
            su[x] = counter+1
            temp.append(values['class_name'])
            new_dict[x] = temp
            dict2 [x] = {
                'class_name' : new_dict[x],
                'smell_name' : 'LPL',
                'value' : su[x]
            }

    for keys, values in lm.items():
        gen = (x for x in lis if x == keys)
        for x in gen:
            su[x] += 1
            temp.append(values['class_name'])
            new_dict[x] = temp
            dict2 [x] = {
            'smell_name' : 'LM',
            'class_name' : new_dict[x],
            'value' : su[x]
            }
            # print(values['class_name'])

    # for keys, values in lbcl.items():
    #     gen = (x for x in lis if x == keys)
    #     for x in gen:
    #         su[x] += 1
    #         dict2 [x] = {
    #         'smell_name' : 'LBCL',
    #         # 'class_name' : values['class_name'],
    #         'value' : su[x]
    #         }

    # for keys, values in lc.items():
    #     gen = (x for x in lis if x == keys)
    #     for x in gen:
    #         su[x] += 1
    #         dict2 [x] = {
    #         'smell_name' : 'LC',
    #         'class_name' : values['class_name'],
    #         'value' : su[x]
    #         }
    #         # print(values['class_name'])

    # for keys, values in sak.items():
    #     gen = (x for x in lis if x == keys)
    #     for x in gen:
    #         su[x] += 1
    #         dict2 [x] = {
    #         'smell_name' : 'SAK',
    #         'class_name' : values['class_name'],
    #         'value' : su[x]
    #         }
    #         # print(values['class_name'])


    # for keys, values in data_class.items():
    #     gen = (x for x in lis if x == keys)
    #     for x in gen:
    #         su[x] += 1
    #         dict2 [x] = {
    #         'smell_name' : 'Data_Class',
    #         'class_name' : values['class_name'],
    #         'value' : su[x]
    #         }
            # print(values['class_name'])

    return dict2


@app.route('/hotspot', methods=['GET'])
def hotspot_analysis():
    
    return(render_template('hotspot_analysis.html'))


@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'username' in session:

        bar_labels = labels
        bar_values = values
        from Design_Smells import DesignSmells
        obj = DesignSmells()
        #1
        lpl = obj.detect_LPL()
        #2
        lm = obj.detect_LM()
        #3
        lbcl = obj.detect_LBCL()
        #4
        lc = obj.large_class()
        lc_len = len(lc)
        #5 remaining
        sak = obj.swiss_army_knife()
        #6
        data_class = obj.data_class()
        total = len(lpl) + len(lm) + len(lbcl) + lc_len + len(sak) + len(data_class)
        obj = getFile()
        lis = obj.get_fileName()
        codes = len(lis)
        return render_template('dashboard.html', title='Lines of Codes Uploaded each Month', total = total, max=4800, labels=bar_labels, values=bar_values,
        codes = codes)

    return render_template('login.html')


@app.route('/summary')
def summary():

    lis = obj.get_fileName()
    files_array = []
    dict = {}
    dict2 = {}
    for files in lis:
        files_array.append(files)
        dict[files] = metrics_obj.get_LOC(files)
        dict2[files] = metrics_obj.get_SLOC(files)

    labels = [
        'LOC', 'SLOC', 'NOM', 'NOPM',
        'NOF'
    ]
    list2 = []
    list2.append(metrics_obj.get_LOC(files))
    list2.append(metrics_obj.get_SLOC(files))
    list2.append(metrics_obj.Number_of_methods(files))
    list2.append(metrics_obj.Number_of_public_methods(files))
    list2.append(metrics_obj.Number_of_fields(files))
    values = list2

    return render_template('summary.html', files=files_array, loc=dict, sloc=dict2, klass=obj.get_classes(), title='Bar-Chart Analysis', max=200, labels=labels, values=values)


@app.route('/export')
def pdf_template():

    path_wkhtmltopdf = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'

    config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
    rendered = render_template('summary.html')
    pdf = pdfkit.from_string(rendered, False, configuration=config)

    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'inline; filename=output.pdf'

    return response


labels = [
    'JAN', 'FEB', 'MAR', 'APR',
    'MAY', 'JUN', 'JUL', 'AUG',
    'SEP', 'OCT', 'NOV', 'DEC'
]

values = [
    100, 253, 1000, 200,
    2328, 2504, 2873, 4764,
    4800, 600, 990, 900
]

colors = [
    "#F7464A", "#46BFBD", "#FDB45C", "#FEDCBA",
    "#ABCDEF", "#DDDDDD", "#ABCABC", "#4169E1",
    "#C71585", "#FF4500", "#FEDCBA", "#46BFBD"]


def get_CC(file):
    method = metrics_obj.cyclomatic_complexity(file)
    i = 1
    list = []
    while i < len(method) - 1:
        temp = method[i].split("(")
        temp2 = temp[1].split(')')
        list.append(temp2[0])
        i += 1
    return list


def compare_NOM(file):
    temp = []
    if metrics_obj.Number_of_methods(file) <= 6:
        temp.append("Lies within Normal Threshold")
    elif 6 < metrics_obj.Number_of_methods(file) <= 14:
        temp.append("Casual/Quuite above threshold")
    elif metrics_obj.Number_of_methods(file) > 14:
        temp.append("Violation")
    return temp


def compare_NOF(file):
    temp = []
    if metrics_obj.Number_of_fields(file) <= 3:
        temp.append("Lies within Normal Threshold")
    elif 3 < metrics_obj.Number_of_fields(file) <= 8:
        temp.append("Casual/Quuite above threshold")
    elif metrics_obj.Number_of_fields(file) > 8:
        temp.append("Violation")
    return temp


def get_lcom4(file):
    list = []
    for x in metrics_obj.lcom4(file):
        if (x != '' and x != '+-----------------------------+------+' and x != 'Calculating LCOM using LCOM4'):
            n = 2
            i = (re.findall("|".join(["[^|]+"]*n), x))
            if (i[1] != ' LCOM '):
                list.append(i[1])
    return list


def compare_LCOM(file):

    temp = []
    for x in get_lcom4(file):

        if float(x) <= 2:
            temp.append("cohesive class, which is the good class")
        elif 2 < float(x) <= 4:
            temp.append("problem, the class should be split into many classes")
        elif float(x) > 4:
            temp.append("no methods in a class")
    return temp


def compare_CC(file):
    for i in get_CC(file):
        if int(i) <= 2:
            return "Good/Commomn"
        elif 2 < int(i) <= 4:
            return "Regular/Casual"
        elif int(i) > 4:
            return "Violation/Bad"


def compare_WMC(file):

    for x, y in metrics_obj.get_WMC(file).items():
        if y <= 11:
            return x, "Good/Common"
        elif 11 < y <= 34:
            return x, "Regular/Casual"
        elif y > 34:
            return x, "Violation/Bad"


def compare_NOP(file):

    temp = []
    for x, y in metrics_obj.Number_of_parameters_(file).items():

        if y <= 2:
            temp.append("Good/Common")
        elif 2 < y <= 4:
            temp.append("Regular/Casual")
        elif y > 4:
            temp.append("Violation/Bad")
    return temp

def compare_NOA(file):

    temp = []
    for x, y in metrics_obj.Number_of_accessors(file).items():

        if y <= 4:
            temp.append("Good/Common")
        elif y > 4:
            temp.append("Violation/Bad")
    return temp

def compare_NOM_LOC(file):

    temp = []
    for x,val in metrics_obj.get_NOML(file).items():
        val = len(val)
        if val <= 10:
            temp.append("Good/Common")
        elif 10 < val <= 32:
            temp.append("Regular/Casual")
        elif val > 32:
            temp.append("Violation/Bad")
    return temp


if __name__ == '__main__':
    app.secret_key = 'secret123'
    app.run(debug=True, threaded=True)
