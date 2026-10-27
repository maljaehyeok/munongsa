FROM nginx:stable-alpine

COPY index.html /usr/share/nginx/html/index.html
COPY assets/ /usr/share/nginx/html/assets/
COPY data/smart-agriculture-catalog.json \
     data/crop-cultivation-records.json \
     data/support-programs.json \
     data/support-public.json \
     data/support-review.json \
     data/finance-products.json \
     data/equipment-catalog.json \
     /usr/share/nginx/html/data/

EXPOSE 80
