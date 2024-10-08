

from datetime import timezone
import json
import logging
from venv import logger
from django.conf import settings
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.views.generic import *
from .forms import AuthenticatedPostCreateForm, UnauthenticatedPostCreateForm
from .models import Post,PostLikes,PostComments,Category,Language
from django.http import Http404, JsonResponse
from django.contrib.auth.models import AnonymousUser
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from django.middleware.csrf import get_token
from django.utils.text import slugify
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages



logger = logging.getLogger(__name__)






class PostListView(ListView):
    model = Post
    template_name = 'posts/home.html'
    context_object_name = 'posts'
    login_url = "account_app:login"

    def post(self, request, *args, **kwargs):
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
                language_name = data.get('language')
                category_name = data.get('category')
                
                # Store the language and category in the session
                if language_name:
                    self.request.session['language'] = language_name
                    print(f"requested language is {language_name}")
                if category_name:
                    self.request.session['category'] = category_name
                    print(f"requested category is {category_name}")
                
                return JsonResponse({'status': 'success', 'message': f'Data received successfully: language={language_name}, category={category_name}'})
            except json.JSONDecodeError:
                return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
        else:
            return JsonResponse({'status': 'error', 'message': 'Unsupported Media Type'}, status=415)


    def get_queryset(self):
        query = self.request.GET.get("q", "").strip()
        language_name = self.request.session.get('language')
        category_name = self.request.session.get('category')

        # Base filter for published posts
        filters = Q(published=True)

        if query:  # If search query is present, filter only by query
            print(f"Search query: {query}")
            filters &= (Q(title__icontains=query) | Q(content__icontains=query))
        else:  # If no search query, filter by language and category
            # Add language filter if available
            if language_name:
                try:
                    language_instance = Language.objects.get(name=language_name)
                    print("language selected")
                    filters &= Q(language=language_instance)
                except Language.DoesNotExist:
                    pass  # If the language is not found, don't filter by language

            # Add category filter if available
            if category_name:
                try:
                    category_instance = Category.objects.get(name=category_name)
                    print("category selected")
                    filters &= Q(category=category_instance)
                except Category.DoesNotExist:
                    pass  # If the category is not found, don't filter by category

        print(f"Filters applied: {filters}")
        # Fetch the filtered queryset
        queryset = Post.objects.filter(filters).order_by('-created', 'title')
        print(f"Queryset results: {[post.title for post in queryset]}")
        return queryset



    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['csrf_token'] = get_token(self.request)

        # Fetch all posts (no pagination)
        posts = self.get_queryset()

        # Set image URLs for the posts
        for post in posts:
            post.image_url = post.thumbnail.url if post.thumbnail else settings.MEDIA_URL + 'post/default/default_thumbnail.png'
        
        context['posts'] = posts
        context['show_subheader'] = True

        return context

    













class PostDetailView(DetailView):
    model = Post
    template_name = 'posts/detailview.html'
    # template_name = 'posts/postdetailpage.html'
    context_object_name = 'post'

    def get_object(self):
        slug = self.kwargs.get("slug")
        if not slug:
            raise Http404("No Post matches the given query.")
        return get_object_or_404(Post, slug=slug)

    def get_queryset(self):
        return Post.objects.prefetch_related('postlikes_set', 'postcomments_set')
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def get_random_posts(self):
        random_posts=Post.objects.filter(published=True).order_by('?')[:10]
        for post in random_posts:
            post.image_url = post.thumbnail.url if post.thumbnail else settings.MEDIA_URL + 'post/default/default_thumbnail.png'  
        return random_posts
    
    def get_related_posts(self, post):
        related_posts = Post.objects.filter(published=True,category=post.category).exclude(slug=post.slug).order_by('-created')[:10]
        for related_post in related_posts:
            related_post.image_url = related_post.thumbnail.url if related_post.thumbnail else settings.MEDIA_URL + 'post/default/default_thumbnail.png'
        return related_posts


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['csrf_token'] = get_token(self.request)
        user = self.request.user
        post = self.get_object()
        context['share_post_description']="Check this out!"
        context['share_post_thumbnail']=self.request.build_absolute_uri(post.thumbnail.url)
        context['share_post_title']=post.title
        context['share_post_url']=self.request.build_absolute_uri(post.get_absolute_url())
        ip_address=self.get_client_ip(self.request)
        check_like= PostLikes.objects.filter(ip_address=ip_address, post=post).exists()
        
        # Ensure user is authenticated
        if check_like:
            print(f"{ip_address} is liked the post already ")
            context['user_liked'] = True  
        else:
            print(f"{ip_address} is did not liked the post already ")
            context['user_liked'] = False 

        
        check_user=self.request.user.is_authenticated
        context["check_user"]=check_user

        context['random_posts'] = self.get_random_posts()
        context['related_posts'] = self.get_related_posts(post)
        context['show_subheader']=False
        
        return context


        # user = request.user
        # slug = request.POST["slug"]
        # post = get_object_or_404(Post, slug=slug)




    def post(self, request, *args, **kwargs):
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
                name = data.get('name')
                email = data.get('email')
                comment_text = data.get('comment')
                like=data.get('like')
                slug = data.get('slug')
                user = request.user
                post = get_object_or_404(Post, slug=slug)
                session_id = request.session.session_key
                ip_address = self.get_client_ip(request)
                print(f"Received data: Name: {name}, Email: {email}, Comment: {comment_text}, Slug: {slug}")

                if comment_text:
                    add_comment = PostComments.objects.create(
                        post=post,
                        text=comment_text,
                        user=user if user.is_authenticated else None,
                        name=name if not user.is_authenticated else '',
                        email=email if not user.is_authenticated else '',
                        ip_address=ip_address,
                        session_id=session_id,
                        published=False
                    )
                post.comments_count = PostComments.objects.filter(post=post).count()
                post.save(update_fields=['comments_count'])
                

                if like: 
                    like_instance=PostLikes.objects.filter(ip_address=ip_address)
                    if not like_instance.exists():
                        PostLikes.objects.create(
                            user=user if user.is_authenticated else None,
                            post=post,
                            ip_address=ip_address,
                            session_id=session_id
                            )
                        Liked=True
                        print(f"{request.user.username} is already to liked the post")
                    else:
                        like_instance.delete()
                        Liked=False
                        print(f"{request.user.username} is not to liked the post")
                    post.likes_count = PostLikes.objects.filter(post=post).count()
                    post.save(update_fields=['likes_count'])
                    return JsonResponse({
                        'liked':Liked,
                        'likes_count':post.likes_count,

                        })

                return JsonResponse({'status': 'success'}, status=200)

            except json.JSONDecodeError as e:
                return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

            except Post.DoesNotExist as e:
                return JsonResponse({'status': 'error', 'message': 'Post not found'}, status=404)

            except Exception as e:
                return JsonResponse({'status': 'error', 'message': 'Server error'}, status=500)

        # If not a JSON request, proceed with the default form handling
        return super().post(request, *args, **kwargs)
        







# Create Post
class PostCreateView(CreateView):
    model = Post
    template_name = 'posts/createpost.html'
    success_url = reverse_lazy('blogpost:post-home')

    def get_form_class(self):
        if self.request.user.is_authenticated:
            return AuthenticatedPostCreateForm
        else:
            return UnauthenticatedPostCreateForm

    def form_valid(self, form):
        session_id = self.request.session.session_key
        ip_address = self.request.META.get('REMOTE_ADDR')
        form.instance.session_id = session_id
        form.instance.ip_address = ip_address
        if self.request.user.is_authenticated:
            form.instance.author = self.request.user

        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['show_subheader'] = False  
        return context
    



# Update Post
class PostUpdateView(LoginRequiredMixin,UpdateView):
    model = Post
    template_name = 'posts/updatepost.html'
    success_url = reverse_lazy('blogpost:user-dashboard')
    login_url=reverse_lazy('blogpost:post-home')
    

    def get_form_class(self):
        if self.request.user.is_authenticated:
            print("registered post create form triggering")
            return AuthenticatedPostCreateForm
           
        else:
            print("anonymous post create form triggering ")
            return UnauthenticatedPostCreateForm


    def form_valid(self, form):
        post = form.save(commit=False)
        
        # Update the slug if the title has changed
        if post.title and post.title != Post.objects.get(pk=post.pk).title:
            post.slug = slugify(post.title)
        # Capture the session ID and IP address
        session_id = self.request.session.session_key
        ip_address = self.request.META.get('REMOTE_ADDR')
        
        # Optionally, add these details to your model
        form.instance.session_id = session_id
        form.instance.ip_address = ip_address
        post.published=False
        post.save()
        messages.success(self.request, f"The post {post.title} has been successfully updated.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['show_subheader'] = False  
        return context
    


class PostDeleteView(LoginRequiredMixin, DeleteView):
    model = Post
    template_name = 'posts/deletepost.html'
    success_url = reverse_lazy('blogpost:user-dashboard')
    login_url = reverse_lazy('blogpost:post-home')
    print(" delete class")

    def delete(self, request, *args, **kwargs):
        print("Inside delete method")
        logger.info("Inside delete method")
        messages.success(self.request, "The post has been successfully deleted.")
        return super().delete(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['show_subheader'] = False  
        return context
    



class UserDashBoard(LoginRequiredMixin,ListView):
    model = Post
    template_name = 'posts/user_dashboard.html'  
    login_url=reverse_lazy('blogpost:post-home')

    def get_queryset(self):
        user = self.request.user
        return Post.objects.filter(author=user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context['published_posts'] = Post.objects.filter(author=user, published=True)
        context['bending_posts'] = Post.objects.filter(author=user, published=False)
        context['published_count'] = Post.objects.filter(author=user, published=True).count()
        context['bending_count'] =Post.objects.filter(author=user, published=False).count()
        context['show_subheader']=False
        return context
    

class UserDashboardPostDetailView(LoginRequiredMixin,DetailView):

    model = Post
    template_name = 'posts/user_dashboard_post_detailview.html'  
    login_url=reverse_lazy('blogpost:post-home')

    def get_object(self):
        slug = self.kwargs.get("slug")
        return get_object_or_404(Post, slug=slug, author=self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['show_subheader'] = False  
        return context
    

class TutorialsView(TemplateView):
    template_name = 'posts/tutorial.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['show_subheader'] = False  
        return context





from .models import DeviceToken

class RegisterDeviceView(View):
    def post(self, request, *args, **kwargs):
        print("hey POST method triggered")
        token = request.POST.get('token')
        if token:
            DeviceToken.objects.get_or_create(token=token)
            print("hey POST method triggered and token is generated")
            return JsonResponse({'status': 'success'})
        return JsonResponse({'status': 'failed'})
