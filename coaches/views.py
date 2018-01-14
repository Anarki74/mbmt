from django.contrib import auth
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404

from . import models, forms
from home.forms import PrettyHelper


def competition_required(view):
    """Wrap a view to require there to be a current competition."""

    def wrapper(request, *args, **kwargs):
        current = models.Competition.current()
        if current is None:
            return redirect("coaches:inactive")

        # Try to pass to function
        try:
            return view(request, *args, competition=current, **kwargs)
        except TypeError:
            return view(request, *args, **kwargs)

    return wrapper


def school_required(view):
    """Wrap a view to require the user to have a school."""

    def wrapper(request, *args, **kwargs):
        coaching = models.Coaching.objects.get(coach=request.user, competition__active=True)
        if coaching is None:
            return redirect("coaches:school")

        # Try to pass to view
        try:
            return view(request, *args, school=coaching.school, **kwargs)
        except TypeError:
            return view(request, *args, **kwargs)

    return wrapper


# The first step in the registration process is for potential coaches
# to register for actual user accounts. This is decoupled from the
# school selection process.

def register(request):
    """The registration page for school sponsors."""

    competition = models.Competition.current()

    # Assert post and form is valid
    if request.method == "POST":
        if competition is None:
            return redirect("coaches:register")

        form = forms.RegisterForm(request.POST)
        if form.is_valid():

            # Create user and school
            user = User.objects.create_user(
                form.cleaned_data["username"],
                email=form.cleaned_data["username"],
                password=form.cleaned_data["password"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"])

            # Login the user and redirect
            user = auth.authenticate(username=user.get_username(), password=form.cleaned_data["password"])
            auth.login(request, user)
            return redirect("coaches:school")

    # Redirect if the user is authenticated already
    elif request.user.is_authenticated:
        return redirect("coaches:index")

    # Otherwise create a new form
    else:
        form = forms.RegisterForm()

    return render(request, "coaches/register.html", {"form": form, "competition": competition})


# Dead view for if there is no active competition.

@login_required
def inactive(request):
    """Show there no active competition."""

    return render(request, "coaches/inactive.html")


# The second step in registration is for the coach to select the
# school which they will represent for the currently active
# competition. If a school has already been claimed by another user,
# this should lead to the duplicate view.

@login_required
@competition_required
def schools(request):
    """Allow the coach to select a school for the current competition."""

    if models.Coaching.objects.filter(coach=request.user, competition__active=True).exists():
        return redirect("coaches:index")

    existing = None

    if request.method == "POST":
        form = forms.SchoolForm(request.POST)
        if form.is_valid():

            if form.use_other:
                school = models.School.objects.create(name=form.cleaned_data["school"])
                school.save()
            else:
                school = models.School.objects.get(name=form.cleaned_data["school"])

            # Check if someone is already coaching
            existing = models.Coaching.objects.filter(
                school__name=form.cleaned_data["school"],
                competition__active=True).first()

            if existing is None:
                models.Coaching.objects.create(
                    school=school,
                    coach=request.user,
                    competition=models.Competition.current()).save()
                return redirect("coaches:index")

    else:
        form = forms.SchoolForm()

    return render(request, "coaches/school.html", {
        "form": form,
        "competition": models.Competition.current(),
        "schools": models.School.objects.values_list("name", flat=True),
        "existing": existing})


# The actual coach dashboard. Also multiplexes general requests for
# users partway through the registration process.

@login_required
@competition_required
@school_required
def index(request, school=None, competition=None):
    """Coach dashboard."""

    return render(request, "coaches/teams.html", {"school": school, "competition": competition})


@login_required
def display_teams(request):
    """Display current teams."""

    return render(request, "coaches/teams.html", {"competition": models.Competition.current()})


@login_required
def edit_team(request, pk=None):
    """Add a team to the list."""

    competition = models.Competition.current()
    if not competition:
        return redirect("home:logout")

    team = None
    students = models.Student.objects.none()

    if pk:
        team = get_object_or_404(models.Team, id=pk)
        students = team.students.all()

    team_form = forms.TeamForm(instance=team)
    student_forms = forms.StudentFormSet(queryset=students)

    # Register a team from posted data
    if request.method == "POST":
        team_form = forms.TeamForm(request.POST, instance=team)
        student_forms = forms.StudentFormSet(request.POST, queryset=students)

        # Check validity and create team
        if team_form.is_valid() and student_forms.is_valid():

            # If not editing existing
            if team:
                team.save()
            else:
                team = team_form.save(commit=False)
                team.school = request.user.school
                team.save()

            form_students = student_forms.save(commit=False)
            for student in form_students:
                student.team = team
                student.save()

            return redirect("teams")

    # Render the form view
    return render(request, "coaches/team.html", {
        "team_form": team_form,
        "student_forms": student_forms,
        "student_helper": PrettyHelper()})


@login_required
def remove_team(request, pk=None):
    """Remove the team."""

    if pk:
        models.Team.objects.filter(id=pk).delete()
    return redirect("teams")
