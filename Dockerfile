FROM odoo:18.0
USER root

COPY ./requirements.txt /requirements.txt
RUN pip3 install -r /requirements.txt --break-system-packages
RUN rm /requirements.txt
RUN mkdir -p /opt/odoo/odoo \
    && ln -sfn /usr/lib/python3/dist-packages/odoo/addons /opt/odoo/odoo/addons \
    && ln -sfn /usr/bin/odoo /opt/odoo/odoo/odoo-bin
