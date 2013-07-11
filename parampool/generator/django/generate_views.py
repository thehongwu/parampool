def generate_views(compute_function,
                   classname,
                   outfile,
                   output_template,
                   menu_function,
                   output_models):

    output_models = output_models.strip(".py")
    compute_function_name = compute_function.__name__
    compute_function_file = compute_function.__module__

    if menu_function:
        menu_function_name = menu_function.__name__
        menu_function_file = menu_function.__module__
        menu = True
    else:
        menu = False

    import inspect
    arg_names = inspect.getargspec(compute_function).args
    defaults  = inspect.getargspec(compute_function).defaults

    # Add code for file upload only if it is strictly needed
    file_upload = False

    if menu:
        # FIXME: This should be replaced by a good regex
        filetxt = ("widget='file'", 'widget="file"',
                   "widget = 'file'", 'widget = "file"')
        menutxt = open(menu_function_file + ".py", 'r').read()
        for txt in filetxt:
            if txt in menutxt:
                file_upload = True
                break
    else:
        for name in arg_names:
            if 'filename' in name:
                file_upload = True
                break

    code = '''\
from django.shortcuts import render_to_response
from django.template import RequestContext
from %(output_models)s import %(classname)sForm
from %(compute_function_file)s import %(compute_function_name)s as compute_function
''' % vars()

    if menu:
        code += '''
# Menu object
from %(menu_function_file)s import %(menu_function_name)s
menu = menu_function()
''' % vars()

    if file_upload:
        code += '''
import os
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
if not os.path.isdir(UPLOAD_DIR):
    os.mkdir(UPLOAD_DIR)
'''

    code += '''
def index(request):
    result = None
'''

    if file_upload and menu:
        code += '''
    form = %(classname)sForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        for field in form:
            if field.name in request.FILES:
                filename = field.data.name
                menu.set_value(field.name, filename)
                with open(os.path.join(UPLOAD_DIR, filename), 'wb+') as destination:
                    for chunk in field.data.chunks():
                        destination.write(chunk)
            else:
                menu.set_value(field.name, field.data)
        result = compute(menu)
        form = %(classname)sForm(request.POST, request.FILES)
''' % vars()

    elif file_upload and not menu:
        code += '''
    filename = None
    form = %(classname)sForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        for field in form:
            if field.name in request.FILES:
                filename = field.data.name
                with open(os.path.join(UPLOAD_DIR, filename), 'wb+') as destination:
                    for chunk in field.data.chunks():
                        destination.write(chunk)
        form = form.save(commit=False)
        request.session["filename"] = filename
        result = compute(form, request)
        form = %(classname)sForm(request.POST, request.FILES)
''' % vars()

    elif not file_upload and menu:
        code += '''
    form = %(classname)sForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        for field in form:
            menu.set_value(field.name, field.data)
        result = compute(menu)
        form = %(classname)sForm(request.POST)
''' % vars()

    else:
        code += '''
    form = %(classname)sForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form = form.save(commit=False)
        result = compute(form)
        form = %(classname)sForm(request.POST or None)
''' % vars()

    code += '''
    return render_to_response(
        "%(output_template)s",
        {"form": form,
         "result": result},
        context_instance=RequestContext(request))

''' % vars()

    if menu:
        code += '''
def compute(menu):
    """
    Generic function for compute_function with values
    taken from the menu object.
    Return the output from the compute_function.
    """

    # If compute_function only has one argument (named menu),
    # send only the menu object itself to the function.
    import inspect
    arg_names = inspect.getargspec(compute_function).args
    if len(arg_names) == 1 and arg_names[0] == "menu":
        return compute_function(menu)

    # Else, extract values from menu and send them to
    # compute_function.
    values = [menu.get(name).get_value() for name in arg_names]
    return compute_function(*values)
'''

    else:
        if file_upload:
            code += '''
def compute(form, request):
'''
        else:
            code += '''
def compute(form):
'''
        code += '''
    """
    Generic function for compute_function with arguments
    taken from a form object (django.forms.ModelForm subclass).
    Return the output from the compute_function.
    """
    # Extract arguments to the compute function
    import inspect
    arg_names = inspect.getargspec(compute_function).args
'''

        if file_upload:
            code += '''

    form_data = []
    for name in arg_names:
        if name != "filename":
            if hasattr(form, name):
                form_data.append(getattr(form, name))
        else:
            form_data.append(request.session.get("filename"))
'''
        else:
            code += '''

    # Extract values from form
    form_data = [getattr(form, name) for name in arg_names
                 if hasattr(form, name)]
'''

        # Give a warning and insert helper code if positional
        # arguments because the user must then convert form_data
        # elements explicitly.
        import inspect
        arg_names = inspect.getargspec(compute_function).args
        defaults  = inspect.getargspec(compute_function).defaults
        if defaults is not None and len(defaults) != len(arg_names):
            # Insert example on argument conversion since there are
            # positional arguments where default_field might be the
            # wrong type
            code += '''
    # Convert data to right types (if necessary)
    # for i in range(len(form_data)):
    #    name = arg_names[i]
    #    if name == '...':
    #         form_data[i] = int(form_data[i])
    #    elif name == '...':
'''
        else:
            # We have default values: do right conversions
            code += '''
    defaults  = inspect.getargspec(compute_function).defaults

    # Make defaults as long as arg_names so we can traverse both with zip
    if defaults:
        defaults = ["none"]*(len(arg_names)-len(defaults)) + list(defaults)
    else:
        defaults = ["none"]*len(arg_names)

    # Convert form data to the right type:
    import numpy
    for i in range(len(form_data)):
        if defaults[i] != "none":
            #if isinstance(defaults[i], (str,bool,int,float)): # bool not ready
            if isinstance(defaults[i], (str,int,float)):
                pass  # special widgets for these types do the conversion
            elif isinstance(defaults[i], numpy.ndarray):
                form_data[i] = numpy.array(eval(form_data[i]))
            elif defaults[i] is None:
                if form_data[i] == 'None':
                    form_data[i] = None
                else:
                    try:
                        # Try eval if it succeeds...
                        form_data[i] = eval(form_data[i])
                    except:
                        pass # Just keep the text
            else:
                # Use eval to convert to right type (hopefully)
                try:
                    form_data[i] = eval(form_data[i])
                except:
                    print 'Could not convert text %s to %s for argument %s' % (form_data[i], type(defaults[i]), arg_names[i])
                    print 'when calling the compute function...'
'''

        code += '''
    # Run computations
    result = compute_function(*form_data)
    return result
''' % vars()

    if outfile is None:
        return code
    else:
        out = open(outfile, 'w')
        out.write(code)
        out.close()
