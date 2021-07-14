import uvicorn
from fastapi import FastAPI, Request, Form, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from datetime import datetime
from typing import Optional
import markdown
from tools import mailer, htmlgen, configuration
from deta import Deta
from dotenv import load_dotenv
import os
from bs4 import BeautifulSoup
import smtplib, ssl

load_dotenv()
app = FastAPI()
deta = Deta(os.getenv("DETA_TOKEN"))

app.mount("/assets", StaticFiles(directory="templates/assets"), name="assets")
app.mount("/setup/assets", StaticFiles(directory="templates/assets"), name="assets")
app.mount("/unsubscribe/assets", StaticFiles(directory="templates/assets"), name="assets")
app.mount("/verify/assets", StaticFiles(directory="templates/assets"), name="assets")
app.mount("/unsubscribe/assets", StaticFiles(directory="templates/assets"), name="assets")
app.mount("/dashboard/assets", StaticFiles(directory="templates/assets"), name="assets")
app.mount("/dashboard/editor/assets", StaticFiles(directory="templates/assets"), name="assets")
templates = Jinja2Templates(directory="templates")
subscribers = deta.Base("microletter-subscribers")
posts = deta.Base("microletter-posts")
config = deta.Base("microletter-config")



"""
--------------------------------------------------------------------------------------
                                MIDDLEWARES
--------------------------------------------------------------------------------------
"""

@app.middleware('http')
async def add_no_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == "/":
        response.headers["Cache-control"] = "no-store"
    return response



"""
--------------------------------------------------------------------------------------
                                USER FRONT END
--------------------------------------------------------------------------------------
"""

@app.get("/")
async def get_root(request: Request):
    if len(config.fetch(None).items) == 0:
        return RedirectResponse(url="/setup", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("index.html", {"request": request, "newsletter_title": configuration.get("newsletter-title"), "newsletter_description": configuration.get("newsletter-description"), "privacy_link": configuration.get("privacy-link"), "footer_year": str(datetime.now().strftime("%Y"))})

@app.post("/subscribe")
async def post_subscribe(request: Request, email: str = Form(...)):
    if len(subscribers.fetch({"email": email}).items) != 0:
        title = "You're already subscribed!"
        description = "This email is already on our list. Even if you love this newsletter, you can't subscribe two times!"
        return templates.TemplateResponse("error.html", {"request": request, "title": title, "description": description})
        
    entry = subscribers.insert({
            "email": email,
            "subscribed_on": str(datetime.now().strftime("%d. %B %Y")),
            "verified": False
    })
    if mailer.verify(email, entry["key"]) is True:
        title = "Last step: Confirm your email"
        description = "You should've received a confirmation email. Click on the link in the email to confirm your subscription. If you can't find it, look in your spam folder or try again."
        return templates.TemplateResponse("success.html", {"request": request, "title": title, "description": description})
    else:
        title = "Email confirmation failed"
        description = "There was a problem with sending your verification Email."
        return templates.TemplateResponse("error.html", {"request": request, "title": title, "description": description})

@app.get("/verify/{key}")
async def get_verify(request: Request, key: str):
    try:
        entry = subscribers.get(key)
        if entry["verified"] is True:
            title = "Your email is already verified!"
            description = "You don't need to verify your email twice! It's already marked as verified."
            return templates.TemplateResponse("success.html", {"request": request, "title": title, "description": description})
        subscribers.update(key=key, updates={
            "email": entry["email"],
            "subscribed_on": entry["subscribed_on"],
            "verified": True
        })
        title = "Your email was confirmed!"
        description = "You successfully verified your email. You'll now receive all new posts in your inbox. Don't worry, you can also unsubscribe any time at the bottom of the newsletter."
        return templates.TemplateResponse("success.html", {"request": request, "title": title, "description": description})
    except:
        title = "The verification failed!"
        description = "Your email couldn't be verified. Please try again later by clicking on the link in the verification email you've received."
        return templates.TemplateResponse("error.html", {"request": request, "title": title, "description": description})

@app.get("/unsubscribe")
async def get_unsubscribe(request: Request, key: Optional[str] = None):
    if key is not None:
        try:
            subscribers.delete(key)
            title = "Successfully unsubscribed!"
            description = "We're sorry to see you go! Your email was removed from our database."
            return templates.TemplateResponse("success.html", {"request": request, "title": title, "description": description})
        except:
            title = "There was a problem with unsubscribing you"
            description = "There was an error while unsubscribing you. Try again later or contact the newsletter owner to get unsubscribed manually."
            return templates.TemplateResponse("error.html", {"request": request, "title": title, "description": description})
    with open("templates/unsubscribe.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content, status_code=200)

    

"""
--------------------------------------------------------------------------------------
                               ADMIN FRONT END
--------------------------------------------------------------------------------------
"""

@app.get("/dashboard")
async def get_dashboard():
    if len(config.fetch(None).items) == 0:
        return RedirectResponse(url="/setup", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse("/dashboard/home")

@app.get("/dashboard/home", response_class=HTMLResponse)
async def get_home(request: Request, show: Optional[str] = None):
    if len(config.fetch(None).items) == 0:
        return RedirectResponse(url="/setup", status_code=status.HTTP_303_SEE_OTHER)
    if show == "success":
        popup_html = """<div role="alert" class="alert alert-success" style="margin-top: 10px;margin-bottom: 10px;"><span><strong>Done!</strong><br /></span></div>"""
    elif show == "error":
        popup_html = """<div role="alert" class="alert alert-danger" style="margin-top: 10px;margin-bottom: 10px;"><span><strong>Error</strong><br /></span></div>"""
    else:
        popup_html = """"""
        
    return templates.TemplateResponse("dashboard.html", {"request": request, "popup": popup_html, "posts": htmlgen.postcode()})

@app.get("/dashboard/editor", response_class=HTMLResponse)
async def get_editor():
    if len(config.fetch(None).items) == 0:
        return RedirectResponse(url="/setup", status_code=status.HTTP_303_SEE_OTHER)
    with open("templates/editor.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content, status_code=200)

@app.get("/dashboard/subscribers", response_class=HTMLResponse)
async def get_subscribers(request: Request, show: Optional[str] = None):
    if len(config.fetch(None).items) == 0:
        return RedirectResponse(url="/setup", status_code=status.HTTP_303_SEE_OTHER)
    if show == "success":
        popup_html = """<div role="alert" class="alert alert-success" style="margin-top: 10px;margin-bottom: 10px;"><span><strong>Done!</strong><br /></span></div>"""
    elif show == "error":
        popup_html = """<div role="alert" class="alert alert-danger" style="margin-top: 10px;margin-bottom: 10px;"><span><strong>Error</strong><br /></span></div>"""
    else:
        popup_html = """"""
    
    subscribers_html, total, monthly = htmlgen.subscribertable()
    return templates.TemplateResponse("subscribers.html", {"request": request, "popup": popup_html, "total_subscribers": total, "monthly_subscribers": monthly, "subscribers": subscribers_html})

@app.get("/setup", response_class=HTMLResponse)
async def get_setup():
    if len(config.fetch(None).items) != 0:
        raise HTTPException(status_code=404, detail="Not found")
    with open("templates/setup.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content, status_code=200)

"""
--------------------------------------------------------------------------------------
                                    BACK END
--------------------------------------------------------------------------------------
"""

@app.post("/unsubscribe/send")
async def post_unsubscribe_send(request: Request, email: str = Form(...)):
    entry = subscribers.fetch({"email": email}).items
    if len(entry) == 0:
        title = "This user isn't subscribed!"
        description = "Sorry, but the email couldn't be found in our database."
        return templates.TemplateResponse("error.html", {"request": request, "title": title, "description": description})
    if mailer.unsubscribe(email, entry[0]["key"]) is True:
        title = "Last step: Confirm that you want to Unsubscribe"
        description = "We've sent you an email containing a link to unsubscribe. Sorry, but this is a security measure."
        return templates.TemplateResponse("success.html", {"request": request, "title": title, "description": description})
    else:
        title = "There was an error sending the confirmation email"
        description = "Sorry but the unsubscribe confirmation email couldn't be sent. Please try again later."
        return templates.TemplateResponse("error.html", {"request": request, "title": title, "description": description})
    
@app.post("/dashboard/editor/create", response_class=HTMLResponse)
async def post_create(request: Request, title: str = Form(None), content: Optional[str] = Form(None)):
    if content is None or title is None:
        title = "Your post can't be empty!"
        description = "Sorry, but you can't create a post without content. Please go back and fill out the content field to send your post."
        return templates.TemplateResponse("error.html", {"request": request, "title": title, "description": description})
    
    date = str(datetime.now().strftime("%d. %B %Y"))
    html_content = markdown.markdown(content)
    soup = BeautifulSoup(html_content, 'lxml')
    text_content = soup.get_text()
    excerpt = text_content[:50] + "..."
    email_data={
        "post_title": title,
        "post_date": date,
        "post_content": html_content
    }
    
    if mailer.send(email_data) is not True:
        title = "There was an error with sending your email"
        description = "Sorry, but the email couldn't be sent. Please try again later."
        return templates.TemplateResponse("error.html", {"request": request, "title": title, "description": description})
    
    posts.insert({
        "title": title,
        "date": date,
        "html_content": html_content,
        "text_content": text_content,
        "excerpt": excerpt
    })
    
    return RedirectResponse(url="/dashboard/home/?show=success", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/dashboard/subscribers/delete/{key}")
async def get_subscriber_delete(key: str):
    subscribers.delete(key)
    return RedirectResponse(url="/dashboard/subscribers/?show=success", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/dashboard/home/delete/{key}")
async def get_home_delete(key: str):
    posts.delete(key)
    return RedirectResponse(url="/dashboard/home/?show=success", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/setup/test")
async def get_setup_test(request: Request, username: str, password: str, server: str, port: int):
    if len(config.fetch(None).items) != 0:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(server, port, context=context) as server:
            server.login(username, password)
        
        title = "Credentials valid!"
        description = "Successfully connected to the SMTP server with the given credentials!"
        return templates.TemplateResponse("success.html", {"request": request, "title": title, "description": description})
    except Exception as e:
        title = "Credential error!"
        description = "Failed to connect to the SMPT server. Error: {0}".format(e)
        return templates.TemplateResponse("error.html", {"request": request, "title": title, "description": description})
    
@app.post("/setup/complete")
async def post_setup_complete(
    username: str = Form(...), 
    password: str = Form(...), 
    server: str = Form(...), 
    port: int = Form(...), 
    title: str = Form(...), 
    tagline: str = Form(...), 
    description: str = Form(...), 
    fade1: str = Form(...), 
    fade2: str = Form(...), 
    titletext: str = Form(...), 
    name: str = Form(...), 
    privacy: str = Form(...), 
    address: str = Form(...)
    ):
    if len(config.fetch(None).items) != 0:
        raise HTTPException(status_code=404, detail="Not found")
    config.insert({
        "smpt-username": username,
        "smtp-password": password,
        "smpt-server": server,
        "smtp-port": port,
        "newsletter-title": title,
        "newsletter-tagline": tagline,
        "newsletter-description": description,
        "color-fade1": fade1,
        "color-fade2": fade2,
        "color-title": titletext,
        "privacy-name": name,
        "privacy-link": privacy,
        "privacy-address": address
    })
    return RedirectResponse(url="/dashboard/home", status_code=status.HTTP_303_SEE_OTHER)


@app.exception_handler(StarletteHTTPException)
async def my_custom_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return templates.TemplateResponse('errcode.html', {'request': request, "error_code": "404", "error_description": "The requested resource couldn't be found."})
    elif exc.status_code == 500:
        return templates.TemplateResponse('error.html', {'request': request, "title": "500", "description": exc.detail})
    else:
        return templates.TemplateResponse('error.html', {'request': request, "title": "Error", "description": exc.detail})


if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=80)