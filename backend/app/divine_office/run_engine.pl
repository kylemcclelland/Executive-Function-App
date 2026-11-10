#!/usr/bin/perl
# Runs Divinum Officium's own, unmodified officium.pl for ONE request and appends the day data it computed as a trailing comment.
# usage: perl run_engine.pl <horas directory> <query string>
use strict;
use warnings;

my ($dir, $query) = @ARGV;
die "usage: run_engine.pl <horas dir> <query>\n" unless defined $dir && defined $query;
chdir $dir or die "cannot enter $dir: $!\n";
@ARGV = ($query);
$0 = "$dir/officium.pl";    # the engine reads its own script name

END {
    binmode(STDOUT, ':utf8');
    no warnings 'once';
    print "\n<!--DO-META\t", join("\t", map { defined $_ ? $_ : '' } @main::dayname),
        "\twinner=", ($main::winner // ''), "\tcommemoratio=", ($main::commemoratio // ''), "\trank=", ($main::rank // ''), "-->\n";
}
do "./officium.pl";
print STDERR $@ if $@;
