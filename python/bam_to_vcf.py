import sys, os
import optparse
from socket import gethostname
from multiprocessing import Pool

refname = "~/Populus/reference_seqs/populus.trichocarpa.cp.fasta";

def assign_ref( ref ):
    global refname
    refname = ref;
    print("refname is %s\n" % refname);

def stop_err( msg ):
    sys.stderr.write( "%s\n" % msg )
    sys.exit()

def runscript(sample_string):
    host,sample,location = sample_string.split()
    cmd = "$REPOS/phylogenomics/converting/bam_to_vcf.sh %s %s" % (sample, refname)
    os.system(cmd)

def __main__():
    #Parse Command Line
    parser = optparse.OptionParser()
    parser.add_option("-i", "--input", default=None, dest="input",
                      help="A list of files to run script on")
    parser.add_option("-r", "--reference", default=None, dest="ref",
                      help="The reference genome")
    parser.add_option("-p", "--processes", default=1, dest="processes",
                      help="Number of processes to use")
    (options, args) = parser.parse_args()

    try:
        open(options.input, "r").close()
    except TypeError, e:
        stop_err("You need to supply the input file:\n" + str(e))

    try:
        open(options.ref, "r").close()
        cmd = "samtools faidx %s" % (refname)
        os.system(cmd)
    except TypeError, e:
        stop_err("Reference file not found:\n" + str(e))

    assign_ref(options.ref)

    pool = Pool(processes=int(options.processes))

    #read the location file
    handle = open(options.input, "r")
    samples = []
    for line in handle:
        sample = line.rstrip()
        samples.append(sample)
    handle.close()

    pool.map(runscript, samples)

if __name__=="__main__":
    __main__()
