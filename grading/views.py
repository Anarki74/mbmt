from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render, redirect, HttpResponse

import json
import math
import collections
import itertools
import traceback

import frontend.models
from . import models


def columnize(objects, columns):
    """Return a list of rows of a column layout."""

    size = math.ceil(len(objects) / columns)
    return list(itertools.zip_longest(*[objects[i:i+size] for i in range(0, len(objects), size)]))


@permission_required("grading.can_grade")
def view_students(request):
    return render(request, "student_view.html", {
        "students": frontend.models.Student.current().order_by("name").all()})


@permission_required("grading.can_grade")
def view_teams(request):
    return render(request, "team_view.html", {
        "teams": frontend.models.Team.current().order_by("number").all()})


@permission_required("grading.can_grade")
def edit_teams(request):
    return render(request, "team_edit.html", {
        "teams": frontend.models.Team.current().order_by("number").all()})


@permission_required("grading.can_grade")
def score(request, grouping, id, round):
    """Scoring view."""

    competition = models.Competition.current()
    round = competition.rounds.filter(ref=round).first()

    if grouping == "team":
        return score_team(request, id, round)
    elif grouping == "individual":
        return score_individual(request, id, round)


def score_team(request, id, round):
    """Scoring view for a team."""

    # Iterate questions and get answers
    team = frontend.models.Team.objects.filter(id=id).first()
    answers = []
    question_answer = []
    for question in round.questions.order_by("number").all():
        answer = models.Answer.objects.filter(team=team, question=question).first()
        if not answer:
            answer = models.Answer(team=team, question=question)
            answer.save()
        answers.append(answer)
        question_answer.append((question, answer))

    # Update the answers
    if request.method == "POST":
        update_answers(request, answers)
        return redirect("team_view")

    # Render the grading view
    return render(request, "grader.html", {
        "name": team.name,
        "division": team.get_division_display,
        "round": round,
        "question_answer": question_answer,
        "mode": "team"})


def score_individual(request, id, round):
    """Scoring view for an individual."""

    # Iterate questions and get answers
    student = frontend.models.Student.objects.filter(id=id).first()
    answers = []
    question_answer = []
    for question in round.questions.order_by("number").all():
        answer = models.Answer.objects.filter(student=student, question=question).first()
        if not answer:
            answer = models.Answer(student=student, question=question)
            answer.save()
        answers.append(answer)
        question_answer.append((question, answer))

    # Update the answers
    if request.method == "POST":
        update_answers(request, answers)
        return redirect("student_view")

    # Render the grading view
    return render(request, "grader.html", {
        "name": student.name,
        "division": student.team.get_division_display,
        "round": round,
        "question_answer": question_answer,
        "mode": "student"})


def update_answers(request, answers):
    """Update the answers to a round by an individual or group."""

    for answer in answers:
        id = str(answer.question.id)
        if id in request.POST:
            value = None if str(request.POST[id]) == "" else float(request.POST[id])
            if answer.value != value:
                answer.value = value
                answer.save()


@login_required
@permission_required("grading.can_grade")
def shirts(request):
    """Shirt sizes view."""

    teams = frontend.models.Team.current()
    teachers = {}
    totals = collections.Counter()
    for team in teams:
        if team.school.user not in teachers:
            teachers[team.school.user] = [team.school.user, [], collections.Counter()]
        teachers[team.school.user][1].extend(list(team.students.all()))
        for student in team.students.all():
            teachers[team.school.user][2][student.get_size_display()] += 1
            totals[student.get_size_display()] += 1
    for teacher in teachers:
        teachers[teacher][1].sort(key=lambda x: x.name)
    return render(request, "shirts.html", {
        "teachers": list(teachers.values()),
        "totals": totals})


@login_required
@permission_required("grading.can_grade")
def attendance(request):
    """Display the attendance page."""

    # If data is posted
    if request.method == "POST":
        attendance_post(request)
        return redirect("attendance")

    # Format students into nice columns
    students = frontend.models.Student.current().all()
    count = request.GET.get("columns", 4)
    columns = columnize(students, count)
    return render(request, "attendance.html", {"students": columns})


def attendance_post(request):
    """Handle post data from the attendance.

    There's some degree of weirdness here, as check boxes don't post
    anything unless they're checked. To prevent this, hidden inputs
    are included for every check box with the absent value. The final
    result is accessed by getting the list of posted values and
    checking if present is in it. To minimize saves, only students
    whose attendance has changed are modified.
    """

    # Iterate post data for numeric entires
    for iid in filter(lambda x: x.isnumeric(), request.POST):
        student = frontend.models.Student.objects.filter(id=iid).first()

        # Check if student, check present or absent
        if student:
            values = request.POST.getlist(iid)
            if "absent" in values:

                # Modify in database
                attending = "present" in request.POST.getlist(iid)
                if student.attending != attending:
                    student.attending = attending
                    student.save()


@permission_required("grading.can_grade")
def student_name_tags(request):
    """Display a table from which student name tags can be generated."""

    return render(request, "tags_students.html", {"students": frontend.models.Student.current()})


@permission_required("grading.can_grade")
def teacher_name_tags(request):
    """Display a table from which student name tags can be generated."""

    users = frontend.models.User.objects.filter(
        is_staff=False, is_superuser=False, school__isnull=False).order_by("school__name")
    users = list(filter(lambda user: user.school and user.school.teams.count(), users))
    return render(request, "tags_teacher.html", {"teachers": users})


def live(request, round):
    """Get the live guts scoreboard."""

    if round == "guts":
        return render(request, "guts.html")
    else:
        return redirect("student_view")


@permission_required("grading.can_grade")
def live_update(request, round):
    """Get the live scoreboard update."""

    if round == "guts":
        grader = models.Competition.current().grader
        scores = grader.guts_live_round_scores(use_cache_before=20)
        named_scores = dict()
        for division in scores:
            division_name = frontend.models.DIVISIONS_MAP[division]
            named_scores[division_name] = {}
            for team in scores[division]:
                named_scores[division_name][team.name] = scores[division][team]
        return HttpResponse(json.dumps(named_scores).encode())
    else:
        return HttpResponse("{}")


def prepare_individual_scores(scores):
    """Prepare the scores from a question score calculation."""

    divisions = []
    for division in sorted(scores.keys()):
        division_name = frontend.models.DIVISIONS_MAP[division]
        things = []
        for thing in scores[division]:
            things.append((thing.name, scores[division][thing]))
        things.sort(key=lambda x: x[1], reverse=True)
        divisions.append((division_name, things))
    return divisions


def prepare_subject_scores(scores):
    """Prepare scores recursively."""

    divisions = []
    for division in sorted(scores.keys()):
        division_name = frontend.models.DIVISIONS_MAP[division]
        subjects = []
        for subject in scores[division]:
            students = []
            for student in scores[division][subject]:
                students.append((student.name, scores[division][subject][student]))
            students.sort(key=lambda x: x[1], reverse=True)
            subjects.append((frontend.models.SUBJECT_CHOICES_MAP[subject], students))
        subjects.sort(key=lambda x: x[0])
        divisions.append((division_name, subjects))
    return divisions


def prepare_composite_team_scores(guts_scores, guts_z, team_scores, team_z, team_individual_scores, overall_scores):
    """Prepare team scores for scoreboard."""

    divisions = []
    for division in sorted(overall_scores.keys()):
        division_name = frontend.models.DIVISIONS_MAP[division]
        teams = []
        for team in overall_scores[division]:
            teams.append((
                team.name,
                guts_scores[division].get(team, 0),
                guts_z[division].get(team, 0),
                team_scores[division].get(team, 0),
                team_z[division].get(team, 0),
                team_individual_scores[division].get(team, 0),
                overall_scores[division].get(team, 0)))
        teams.sort(key=lambda x: x[-1], reverse=True)
        divisions.append((division_name, teams))
    return divisions


def prepare_school_team_scores(school, guts_scores, team_scores, team_individual_scores, overall_scores):
    """Prepare scores for sponsor scoreboard."""

    divisions = []
    for division in sorted(overall_scores.keys()):
        division_name = frontend.models.DIVISIONS_MAP[division]
        teams = []
        for team in overall_scores[division]:
            if team.school != school:
                continue
            teams.append((
                team.name,
                guts_scores[division].get(team, 0),
                team_scores[division].get(team, 0),
                team_individual_scores[division].get(team, 0),
                overall_scores[division].get(team, 0)))
        teams.sort(key=lambda x: x[-1], reverse=True)
        divisions.append((division_name, teams))
    return divisions


def prepare_school_individual_scores(school, scores):
    """Prepare individual scores for sponsor scoreboard."""

    divisions = []
    for division in scores:
        students = {}
        for i, subject in enumerate(sorted(frontend.models.SUBJECT_CHOICES_MAP.keys())):
            for student in scores[division][subject]:
                if student.team.school != school:
                    continue
                if student not in students:
                    students[student] = [None, None, None, None]
                students[student][i] = scores[division][subject][student]
        students = list(map(lambda x: (x[0].name, x[1]), students.items()))
        students.sort(key=lambda x: x[0])
        divisions.append((frontend.models.DIVISIONS_MAP[division], students))
    return divisions


@login_required
def sponsor_scoreboard(request):
    """Get the sponsor scoreboard."""

    grader = models.Competition.current().grader
    subject_scores = grader.cache_get("subject_scores")
    grader.calculate_team_scores(use_cache=True)
    if subject_scores is None:
        grader.calculate_individual_scores(use_cache=False)

    school = request.user.school
    individual_scores = prepare_school_individual_scores(school, grader.cache_get("subject_scores"))
    team_scores = prepare_school_team_scores(
        school,
        grader.cache_get("raw_guts_scores"),
        grader.cache_get("raw_team_scores"),
        grader.cache_get("team_individual_scores"),
        grader.calculate_team_scores(use_cache=True))

    return render(request, "scoring.html", {
        "individual_scores": individual_scores,
        "team_scores": team_scores
    })


@permission_required("grading.can_grade")
def student_scoreboard(request):
    """Do final scoreboard calculations."""

    grader = models.Competition.current().grader
    if request.method == "POST" and "recalculate" in request.POST:
        grader.calculate_individual_scores(use_cache=False)
        return redirect("student_scoreboard")

    try:
        individual_scores = prepare_individual_scores(grader.calculate_individual_scores(use_cache=True))
        subject_scores = prepare_subject_scores(grader.cache_get("subject_scores"))
        context = {
            "individual_scores": individual_scores,
            "subject_scores": subject_scores,
            "individual_powers": grader.individual_powers,
            "individual_bonus": grader.individual_bonus}
    except Exception:
        context = {"error": traceback.format_exc().replace("\n", "<br>")}
    return render(request, "student_scoreboard.html", context)


@permission_required("grading.can_grade")
def team_scoreboard(request):
    """Show the team scoreboard view."""

    grader = models.Competition.current().grader
    if request.method == "POST" and "recalculate" in request.POST:
        grader.calculate_team_scores(use_cache=False)
        return redirect("team_scoreboard")

    try:
        team_scores = grader.calculate_team_scores(use_cache=True)
        context = {
            "team_scores": prepare_composite_team_scores(
                grader.cache_get("raw_guts_scores"), grader.cache_get("guts_scores"),
                grader.cache_get("raw_team_scores"), grader.cache_get("team_scores"),
                grader.cache_get("team_individual_scores"),
                team_scores)}
    except Exception:
        context = {"error": traceback.format_exc().replace("\n", "<br>")}
    return render(request, "team_scoreboard.html", context)
