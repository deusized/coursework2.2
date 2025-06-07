from django.shortcuts import render, redirect
from django.contrib.auth import login
from .forms import PlayerRegistrationForm

def register_view(request):
    if request.method == 'POST':
        form = PlayerRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('lobby') 
    else:
        form = PlayerRegistrationForm()
    return render(request, 'registration/register.html', {'form': form})