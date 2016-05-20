from urllib import parse

from django.contrib.auth.models import User
from django.conf import settings
from django.core.signing import TimestampSigner
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.core.urlresolvers import reverse

from nightreads.posts.models import Tag
from .models import Subscription


def _update_url_query_param(url, query_params):
    url_parts = parse.urlparse(url)
    old_qs_args = dict(parse.parse_qsl(url_parts[4]))
    old_qs_args.update(query_params)
    new_qs = parse.urlencode(old_qs_args)
    return parse.urlunparse(
        list(url_parts[0:4]) + [new_qs] + list(url_parts[5:]))


def update_user_tags(user, tags):
    tags_objs = Tag.objects.filter(name__in=tags)
    if tags_objs:
        user.subscription.tags.clear()
        user.subscription.tags.add(*tags_objs)
        user.save()
        return True
    return False


def get_or_create_user(email):
    user, created = User.objects.get_or_create(username=email)
    if created:
        Subscription.objects.create(user=user)
    return user


def get_user(email):
    return User.objects.filter(username=email).first()


def generate_key(user, for_subscription=True):
    salt = 'subscription' if for_subscription else 'unsubscription'
    signer = TimestampSigner(settings.SECRET_KEY, salt=salt)
    return signer.sign(str(user.id))


def validate_key(key, user, for_subscription=True):
    salt = 'subscription' if for_subscription else 'unsubscription'
    signer = TimestampSigner(settings.SECRET_KEY, salt=salt)
    value = signer.unsign(key, max_age=settings.EMAIL_LINK_EXPIRY_DAYS)
    return str(user.id) == value


def update_subscription(user, status):
    user.subscription.is_subscribed = status
    user.save()


def verify_subscription_code(user, code):
    if user.subscription.is_subscribed:
        return True


def verify_unsubscription_code(user, code):
    if not user.subscription.is_subscribed:
        return True


def _get_message_and_subject(url, for_subscription=True):
    key = 'subscribe' if for_subscription else 'unsubscribe'
    message_template = 'user_manager/{}.html'.format(key)
    subject_template = 'user_manager/{}_subject.txt'.format(key)
    message = render_to_string(message_template, {'url': url})
    subject = render_to_string(subject_template)
    return message, subject


def send_confirmation_email(request, user, key, for_subscription=True):
    site_url = request.build_absolute_uri(reverse('users:confirm'))
    query_params = dict(
        user=user.id, code=key, subscribe=int(for_subscription))
    url = _update_url_query_param(url=site_url, query_params=query_params)
    message, subject = _get_message_and_subject(
        url=url, for_subscription=for_subscription)
    send_mail(
        subject=subject,
        message=message,
        html_message=message.replace('\n', '<br />'),
        from_email=settings.SENDER_EMAIL,
        recipient_list=[user.username],
    )
