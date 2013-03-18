import datetime
from urllib import urlencode

from django.contrib.syndication.views import Feed
from django.core import urlresolvers
from django.core.paginator import Paginator, InvalidPage, EmptyPage
from django.http import HttpResponse, Http404, HttpResponseRedirect, HttpResponsePermanentRedirect
from django.shortcuts import get_object_or_404
from django.template import Context, loader, RequestContext
from django.template.defaultfilters import date as format_date
from django.views.decorators.vary import vary_on_headers

from parliament.bills.models import Bill, VoteQuestion, MemberVote, BillInSession
from parliament.core.api import ModelListView, ModelDetailView, APIFilters
from parliament.core.models import Session
from parliament.hansards.models import Statement

def bill_pk_redirect(request, bill_id):
    bill = get_object_or_404(Bill, pk=bill_id)
    return HttpResponsePermanentRedirect(
        urlresolvers.reverse('parliament.bills.views.bill', kwargs={
        'session_id': bill.get_session().id, 'bill_number': bill.number}))


class BillDetailView(ModelDetailView):

    def get_object(self, request, session_id, bill_number):
        return BillInSession.objects.select_related(
            'bill', 'sponsor_politician').get(session=session_id, bill__number=bill_number)

    def get_related_resources(self, request, qs, result):
        return {
            'bills_url': urlresolvers.reverse('bills')
        }

    def get_html(self, request, session_id, bill_number):
        PER_PAGE = 10
        bill = get_object_or_404(Bill, sessions=session_id, number=bill_number)
        statements = bill.statement_set.all().order_by('-time', '-sequence').select_related('member', 'member__politician', 'member__riding', 'member__party')
        paginator = Paginator(statements, PER_PAGE)

        try:
            pagenum = int(request.GET.get('page', '1'))
        except ValueError:
            pagenum = 1
        try:
            page = paginator.page(pagenum)
        except (EmptyPage, InvalidPage):
            page = paginator.page(paginator.num_pages)

        c = RequestContext(request, {
            'bill': bill,
            'page': page,
            'votequestions': bill.votequestion_set.all().order_by('-date', '-number'),
            'title': ('Bill %s' % bill.number) + (' (Historical)' if bill.session.end else ''), 
            'statements_full_date': True,
            'statements_context_link': True,
        })
        if request.is_ajax():
            t = loader.get_template("hansards/statement_page.inc")
        else:
            t = loader.get_template("bills/bill_detail.html")
        return HttpResponse(t.render(c))
bill = vary_on_headers('X-Requested-With')(BillDetailView.as_view())
    
class BillListView(ModelListView):

    filters = {
        'session': APIFilters.dbfield(),
        'introduced': APIFilters.dbfield(filter_types=APIFilters.numeric_filters),
        'legisinfo_id': APIFilters.dbfield(),
        'number': APIFilters.dbfield('bill__number'),
        'law': APIFilters.dbfield('bill__law'),
        'private_member_bill': APIFilters.dbfield('bill__privatemember'),
        'sponsor_politician': APIFilters.fkey(lambda u: {'sponsor_politician__slug': u[-1]}),
        'sponsor_politician_role': APIFilters.fkey(lambda u: {'sponsor_member': u[-1]}),
    }

    def get_qs(self, request):
        return BillInSession.objects.all().select_related('bill', 'sponsor_politician')

    def get_html(self, request):
        sessions = Session.objects.with_bills()
        len(sessions) # evaluate it
        bills = Bill.objects.filter(sessions=sessions[0])
        votes = VoteQuestion.objects.select_related('bill').filter(session=sessions[0])[:6]

        t = loader.get_template('bills/index.html')
        c = RequestContext(request, {
            'object_list': bills,
            'session_list': sessions,
            'votes': votes,
            'session': sessions[0],
            'title': 'Bills & Votes'
        })

        return HttpResponse(t.render(c))
index = BillListView.as_view()


class BillSessionListView(ModelListView):

    def get_json(self, request, session_id):
        return HttpResponseRedirect(urlresolvers.reverse('bills') + '?'
                                    + urlencode({'session': session_id}))

    def get_html(self, request, session_id):
        session = get_object_or_404(Session, pk=session_id)
        bills = Bill.objects.filter(sessions=session)
        votes = VoteQuestion.objects.select_related('bill').filter(session=session)[:6]

        t = loader.get_template('bills/bill_list.html')
        c = RequestContext(request, {
            'object_list': bills,
            'session': session,
            'votes': votes,
            'title': 'Bills for the %s' % session
        })
        return HttpResponse(t.render(c))
bills_for_session = BillSessionListView.as_view()


class VoteListView(ModelListView):

    filters = {
        'session': APIFilters.dbfield(),
        'yea_total': APIFilters.dbfield(filter_types=APIFilters.numeric_filters),
        'nay_total': APIFilters.dbfield(filter_types=APIFilters.numeric_filters),
        'paired_total': APIFilters.dbfield(filter_types=APIFilters.numeric_filters),
        'date': APIFilters.dbfield(filter_types=APIFilters.numeric_filters),
        'number': APIFilters.dbfield(filter_types=APIFilters.numeric_filters),
        'bill': APIFilters.fkey(lambda u: {
            'bill__session': u[-2],
            'bill__number': u[-1]
        }),
        'result': APIFilters.choices()
    }

    def get_json(self, request, session_id=None):
        if session_id:
            return HttpResponseRedirect(urlresolvers.reverse('votes') + '?'
                                        + urlencode({'session': session_id}))
        return super(VoteListView, self).get_json(request)

    def get_qs(self, request):
        return VoteQuestion.objects.select_related(depth=1).order_by('-date', '-number')

    def get_html(self, request, session_id=None):
        if session_id:
            session = get_object_or_404(Session, pk=session_id)
        else:
            session = Session.objects.current()

        t = loader.get_template('bills/votequestion_list.html')
        c = RequestContext(request, {
            'object_list': self.get_qs(request).filter(session=session),
            'session': session,
            'title': 'Votes for the %s' % session
        })
        return HttpResponse(t.render(c))
votes_for_session = VoteListView.as_view()
        
def vote_pk_redirect(request, vote_id):
    vote = get_object_or_404(VoteQuestion, pk=vote_id)
    return HttpResponsePermanentRedirect(
        urlresolvers.reverse('parliament.bills.views.vote', kwargs={
        'session_id': vote.session_id, 'number': vote.number}))


class VoteDetailView(ModelDetailView):

    def get_object(self, request, session_id, number):
        return get_object_or_404(VoteQuestion, session=session_id, number=number)

    def get_related_resources(self, request, obj, result):
        return {
            'ballots_url': urlresolvers.reverse('vote_ballots') + '?' +
                urlencode({'vote': result['object']['url']}),
            'votes_url': urlresolvers.reverse('votes')
        }

    def get_html(self, request, session_id, number):
        vote = self.get_object(request, session_id, number)
        membervotes = MemberVote.objects.filter(votequestion=vote)\
            .order_by('member__party', 'member__politician__name_family')\
            .select_related('member', 'member__party', 'member__politician')
        partyvotes = vote.partyvote_set.select_related('party').all()

        c = RequestContext(request, {
            'vote': vote,
            'membervotes': membervotes,
            'parties_y': [pv.party for pv in partyvotes if pv.vote == 'Y'],
            'parties_n': [pv.party for pv in partyvotes if pv.vote == 'N']
        })
        t = loader.get_template("bills/votequestion_detail.html")
        return HttpResponse(t.render(c))
vote = VoteDetailView.as_view()


class BallotListView(ModelListView):

    filters = {
        'vote': APIFilters.fkey(lambda u: {'votequestion__session': u[-2],
                                           'votequestion__number': u[-1]}),
        'politician': APIFilters.fkey(lambda u: {'politician__slug': u[-1]}),
        'politician_role': APIFilters.fkey(lambda u: {'member': u[-1]}),
        'ballot': APIFilters.choices('vote')
    }

    def get_qs(self, request):
        return MemberVote.objects.all()

    def object_to_dict(self, obj):
        return obj.to_api_dict(representation='list')
ballots = BallotListView.as_view()

class BillListFeed(Feed):
    title = 'Bills in the House of Commons'
    description = 'New bills introduced to the House, from openparliament.ca.'
    link = "/bills/"
    
    def items(self):
        return Bill.objects.filter(introduced__isnull=False).order_by('-introduced', 'number_only')[:25]
    
    def item_title(self, item):
        return "Bill %s (%s)" % (item.number,
            "Private member's" if item.privatemember else "Government")
    
    def item_description(self, item):
        return item.name
        
    def item_link(self, item):
        return item.get_absolute_url()
        
    
class BillFeed(Feed):

    def get_object(self, request, bill_id):
        return get_object_or_404(Bill, pk=bill_id)

    def title(self, bill):
        return "Bill %s" % bill.number

    def link(self, bill):
        return "http://openparliament.ca" + bill.get_absolute_url()

    def description(self, bill):
        return "From openparliament.ca, speeches about Bill %s, %s" % (bill.number, bill.name)

    def items(self, bill):
        statements = bill.statement_set.all().order_by('-time', '-sequence').select_related('member', 'member__politician', 'member__riding', 'member__party')[:10]
        votes = bill.votequestion_set.all().order_by('-date', '-number')[:3]
        merged = list(votes) + list(statements)
        merged.sort(key=lambda i: i.date, reverse=True)
        return merged

    def item_title(self, item):
        if isinstance(item, VoteQuestion):
            return "Vote #%s (%s)" % (item.number, item.get_result_display())
        else:
            return "%(name)s (%(party)s%(date)s)" % {
                'name': item.name_info['display_name'],
                'party': item.member.party.short_name + '; ' if item.member else '',
                'date': format_date(item.time, "F jS"),
            }

    def item_link(self, item):
        return item.get_absolute_url()

    def item_description(self, item):
        if isinstance(item, Statement):
            return item.text_html()
        else:
            return item.description

    def item_pubdate(self, item):
        return datetime.datetime(item.date.year, item.date.month, item.date.day)
