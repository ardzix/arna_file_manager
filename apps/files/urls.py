from django.urls import path

from . import views

urlpatterns = [
    path("files", views.FileListView.as_view(), name="file-list"),
    path("files/upload", views.UploadInitiateView.as_view(), name="upload-initiate"),
    path("files/<uuid:file_id>/parts/presign", views.PresignPartsView.as_view(), name="upload-presign-parts"),
    path("files/<uuid:file_id>/complete", views.UploadCompleteView.as_view(), name="upload-complete"),
    path("files/<uuid:file_id>/abort", views.UploadAbortView.as_view(), name="upload-abort"),
    path("files/<uuid:file_id>", views.FileDetailView.as_view(), name="file-detail"),
    path("files/<uuid:file_id>/move", views.FileMoveView.as_view(), name="file-move"),
    path("files/<uuid:file_id>/shares", views.FileShareCreateView.as_view(), name="file-share-create"),
    path("files/<uuid:file_id>/shares/<uuid:share_id>", views.FileShareRevokeView.as_view(), name="file-share-revoke"),
    path("folders/root/children", views.RootChildrenView.as_view(), name="root-children"),
    path("folders", views.FolderCreateView.as_view(), name="folder-create"),
    path("folders/<uuid:folder_id>/children", views.FolderChildrenView.as_view(), name="folder-children"),
]
